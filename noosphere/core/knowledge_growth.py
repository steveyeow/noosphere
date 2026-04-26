"""Knowledge growth: capture from chat, RSS inflow, LLM synthesis, corpus health.

Bridges gaps vs personal LLM-wiki workflows (incremental compile, feeds, chat→KB).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx
import numpy as np

from noosphere.core.config import (
    CONCEPT_RECOMPILE_THRESHOLD,
    CONCEPT_TIMELINE_HEADING,
    CONCEPT_TIMELINE_MAX_MATCHES,
    CONCEPT_TIMELINE_THRESHOLD,
)
from noosphere.core.db import get_conn
from noosphere.core.ingest import ingest_text, ingest_url
from noosphere.core.indexer import index_corpus
from noosphere.core.retrieval import search_corpus

logger = logging.getLogger(__name__)


# ── Living concept notes: compiled-truth + timeline format ────────────────
#
# A concept doc's content is split into two sections by a `## Timeline`
# heading. Above = compiled truth (LLM-written synthesis, rewritten on
# recompile). Below = append-only bullet list of evidence entries, one per
# source doc that matched the concept via the timeline-append hook.

_TIMELINE_SPLIT_RE = re.compile(
    r"\n\s*\n" + re.escape(CONCEPT_TIMELINE_HEADING) + r"\s*\n", re.MULTILINE
)
_TIMELINE_ID_RE = re.compile(r"\[id=([A-Za-z0-9]{6,32})\]")


def _parse_concept_content(content: str) -> tuple[str, list[str]]:
    """Split concept body into ``(compiled_truth, timeline_lines)``.

    Legacy concepts lacking the heading are treated as all compiled-truth
    with an empty timeline, so the next append lazily migrates them.
    """
    match = _TIMELINE_SPLIT_RE.search(content or "")
    if match is None:
        return (content or "").rstrip(), []
    compiled = content[: match.start()].rstrip()
    block = content[match.end():].strip()
    if not block:
        return compiled, []
    lines = [
        ln.rstrip()
        for ln in block.split("\n")
        if ln.lstrip().startswith("- ")
    ]
    return compiled, lines


def _assemble_concept_content(compiled_truth: str, timeline_lines: list[str]) -> str:
    """Serialize ``(compiled_truth, timeline_lines)`` into canonical content form."""
    compiled_truth = (compiled_truth or "").rstrip()
    heading = CONCEPT_TIMELINE_HEADING
    if not timeline_lines:
        return f"{compiled_truth}\n\n{heading}\n\n(no timeline entries yet)\n"
    body = "\n".join(ln.rstrip() for ln in timeline_lines)
    return f"{compiled_truth}\n\n{heading}\n\n{body}\n"


def _extract_timeline_doc_ids(lines: list[str]) -> list[str]:
    """Pull ``doc_id`` tokens from timeline entries like ``[id=abc123…]``."""
    out: list[str] = []
    for ln in lines:
        m = _TIMELINE_ID_RE.search(ln)
        if m:
            did = m.group(1)
            if did and did not in out:
                out.append(did)
    return out


def _find_matching_concepts(
    corpus_id: str,
    query_vec: np.ndarray,
    query_norm: float,
    *,
    exclude_doc_id: str = "",
    threshold: float | None = None,
    max_matches: int | None = None,
) -> list[tuple[str, float]]:
    """Score each concept doc by max chunk similarity to ``query_vec``.

    Returns up to ``max_matches`` ``(concept_doc_id, score)`` pairs with
    ``score >= threshold``, sorted high to low. Empty list when the corpus
    has no concept docs or none pass the threshold. Config defaults are
    resolved at call time so tests can monkeypatch the module constants.
    """
    from noosphere.core.embeddings import blob_to_vector

    if threshold is None:
        threshold = CONCEPT_TIMELINE_THRESHOLD
    if max_matches is None:
        max_matches = CONCEPT_TIMELINE_MAX_MATCHES

    conn = get_conn()
    concept_rows = conn.execute(
        "SELECT id FROM documents WHERE corpus_id=? AND doc_type='concept'",
        (corpus_id,),
    ).fetchall()
    if not concept_rows:
        return []

    concept_ids = {r["id"] for r in concept_rows}
    if exclude_doc_id:
        concept_ids.discard(exclude_doc_id)
    if not concept_ids:
        return []

    placeholders = ",".join("?" for _ in concept_ids)
    chunk_rows = conn.execute(
        f"SELECT document_id, vector, dim, norm FROM chunks "
        f"WHERE corpus_id=? AND document_id IN ({placeholders})",
        (corpus_id, *concept_ids),
    ).fetchall()
    if not chunk_rows:
        return []

    doc_scores: dict[str, float] = {}
    for r in chunk_rows:
        try:
            vec = blob_to_vector(r["vector"], r["dim"])
        except Exception:
            continue
        chunk_norm = r["norm"]
        if not chunk_norm:
            continue
        score = float(np.dot(query_vec, vec) / (query_norm * chunk_norm))
        did = r["document_id"]
        if score > doc_scores.get(did, -1.0):
            doc_scores[did] = score

    filtered = [(did, s) for did, s in doc_scores.items() if s >= threshold]
    filtered.sort(key=lambda x: x[1], reverse=True)
    return filtered[:max_matches]


def _append_timeline_entry(concept_doc_id: str, timeline_line: str) -> bool:
    """Append one bullet line to a concept's timeline section, bump dirty counter.

    Idempotent: if the last timeline line is byte-identical, does nothing.
    Invalidates the concept's index (``indexed_at=NULL``) so the next
    ``index_corpus`` run re-embeds it.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT content, metadata_json FROM documents WHERE id=?",
        (concept_doc_id,),
    ).fetchone()
    if not row:
        return False
    compiled, timeline_lines = _parse_concept_content(row["content"] or "")
    if timeline_lines and timeline_lines[-1].strip() == timeline_line.strip():
        return False
    timeline_lines.append(timeline_line)
    new_content = _assemble_concept_content(compiled, timeline_lines)

    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    meta["timeline_dirty"] = True
    meta["pending_changes"] = int(meta.get("pending_changes", 0) or 0) + 1
    meta["last_timeline_append_at"] = datetime.now(timezone.utc).isoformat()

    conn.execute(
        "UPDATE documents SET content=?, metadata_json=?, word_count=?, indexed_at=NULL "
        "WHERE id=?",
        (
            new_content,
            json.dumps(meta),
            len(new_content.split()),
            concept_doc_id,
        ),
    )
    conn.commit()
    return True


def _append_to_matching_concept_timelines(corpus_id: str, new_doc_id: str) -> list[dict]:
    """Hook: for a newly-ingested doc, update each matching concept's timeline.

    Never raises — all failures logged. Safe to call even when no embedder is
    configured or when the corpus has no concept docs yet.
    """
    from noosphere.core.embeddings import get_embedder
    from noosphere.core.ingest import get_document

    doc = get_document(new_doc_id)
    if not doc:
        return []
    if (doc.get("doc_type") or "") == "concept":
        return []

    try:
        embedder = get_embedder()
    except Exception as e:
        logger.info("concept-timeline hook skipped (no embedder): %s", e)
        return []

    content = (doc.get("content") or "").strip()
    if not content:
        return []
    query_text = content[:3000]
    try:
        qvec = embedder.embed([query_text])[0]
    except Exception as e:
        logger.warning("concept-timeline embed failed for %s: %s", new_doc_id, e)
        return []
    qnorm = float(np.linalg.norm(qvec))
    if qnorm == 0:
        return []

    matches = _find_matching_concepts(
        corpus_id, qvec, qnorm, exclude_doc_id=new_doc_id,
    )
    if not matches:
        return []

    verb = "captured" if (doc.get("doc_type") or "") == "capture" else "ingested"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = (doc.get("title") or "Untitled").strip().replace("\n", " ")[:200]
    entry = f"- {date_str} — {verb}: {title} [id={new_doc_id}]"

    updated: list[dict] = []
    for concept_id, score in matches:
        try:
            changed = _append_timeline_entry(concept_id, entry)
            if changed:
                updated.append({"concept_id": concept_id, "score": round(score, 4)})
        except Exception as e:
            logger.warning("failed to update concept %s timeline: %s", concept_id, e)
    return updated


def _snapshot_concept_version(
    concept_doc_id: str,
    *,
    version: int,
    content: str,
    source_doc_ids: list[str],
) -> None:
    """Store a snapshot of a concept's state in ``concept_versions``."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO concept_versions (id, document_id, version, content, "
        "source_doc_ids, compiled_at) VALUES (?,?,?,?,?,?)",
        (
            uuid.uuid4().hex[:12],
            concept_doc_id,
            version,
            content,
            json.dumps(source_doc_ids or []),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def get_concept_versions(concept_doc_id: str) -> list[dict]:
    """Return all snapshots for a concept, oldest first."""
    rows = get_conn().execute(
        "SELECT id, document_id, version, content, source_doc_ids, compiled_at "
        "FROM concept_versions WHERE document_id=? ORDER BY version ASC",
        (concept_doc_id,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            sources = json.loads(r["source_doc_ids"] or "[]")
        except json.JSONDecodeError:
            sources = []
        out.append({
            "id": r["id"],
            "document_id": r["document_id"],
            "version": r["version"],
            "content": r["content"],
            "source_doc_ids": sources,
            "compiled_at": r["compiled_at"],
        })
    return out


def _llm_recompile_compiled_truth(
    topic: str,
    previous_compiled_truth: str,
    source_doc_ids: list[str],
) -> str:
    """Call the LLM to regenerate compiled truth from sources + prior synthesis."""
    from noosphere.core.llm import call_llm as _call_llm
    from noosphere.core.ingest import get_document

    parts: list[str] = []
    for sid in source_doc_ids[:20]:
        sdoc = get_document(sid)
        if not sdoc:
            continue
        body = (sdoc.get("content") or "").strip()[:4000]
        if not body:
            continue
        stitle = sdoc.get("title") or sid
        parts.append(f"### {stitle}\n{body}")
    if not parts:
        raise ValueError("no source documents available for recompile")
    sources_text = "\n\n---\n\n".join(parts)

    sys = (
        "You maintain the 'compiled truth' section of a living knowledge-base concept note. "
        "Read the prior synthesis and all source materials, then produce a refreshed synthesis "
        "that reflects every source. Preserve accurate prior points, integrate new evidence, "
        "note contradictions; do not invent facts. Return ONLY the new compiled truth in Markdown — "
        "do not include a Timeline section or a '## Timeline' heading. Use the same language as the sources."
    )
    user = (
        f"Concept: {topic}\n\n---\n\n"
        f"Prior compiled truth (may be empty):\n\n{previous_compiled_truth or '(none)'}\n\n---\n\n"
        f"Sources:\n\n{sources_text}\n\n---\n\n"
        "Rewrite the compiled truth now."
    )
    text = _call_llm([{"role": "system", "content": sys}, {"role": "user", "content": user}])
    if not text or text.startswith("No LLM provider"):
        raise ValueError(text or "LLM returned empty output")
    return text.strip()


def recompile_concept_if_dirty(concept_doc_id: str, *, force: bool = False) -> dict:
    """Regenerate a concept's compiled truth if it has accumulated enough pending changes.

    Snapshots the prior version to ``concept_versions`` before rewriting. The
    timeline section is preserved byte-for-byte; only compiled truth changes.
    """
    from noosphere.core.ingest import get_document

    doc = get_document(concept_doc_id)
    if not doc:
        raise ValueError(f"concept document not found: {concept_doc_id}")
    if (doc.get("doc_type") or "") != "concept":
        raise ValueError(f"not a concept document: {concept_doc_id}")

    try:
        meta = json.loads(doc.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        meta = {}
    pending = int(meta.get("pending_changes", 0) or 0)
    dirty = bool(meta.get("timeline_dirty", False))
    current_version = int(meta.get("version", 1) or 1)

    if not force and (not dirty or pending < CONCEPT_RECOMPILE_THRESHOLD):
        return {
            "status": "skipped",
            "reason": "below threshold",
            "concept_id": concept_doc_id,
            "pending_changes": pending,
            "threshold": CONCEPT_RECOMPILE_THRESHOLD,
            "version": current_version,
        }

    compiled, timeline_lines = _parse_concept_content(doc.get("content") or "")
    timeline_source_ids = _extract_timeline_doc_ids(timeline_lines)
    prior_sources = meta.get("source_document_ids") or []
    merged_sources: list[str] = []
    for sid in list(prior_sources) + list(timeline_source_ids):
        if sid and sid not in merged_sources:
            merged_sources.append(sid)

    _snapshot_concept_version(
        concept_doc_id,
        version=current_version,
        content=doc.get("content") or "",
        source_doc_ids=merged_sources,
    )

    new_compiled = _llm_recompile_compiled_truth(
        topic=doc.get("title", ""),
        previous_compiled_truth=compiled,
        source_doc_ids=merged_sources,
    )
    new_content = _assemble_concept_content(new_compiled, timeline_lines)
    new_version = current_version + 1
    meta["version"] = new_version
    meta["timeline_dirty"] = False
    meta["pending_changes"] = 0
    meta["last_compiled_at"] = datetime.now(timezone.utc).isoformat()
    meta["source_document_ids"] = merged_sources[:50]

    conn = get_conn()
    conn.execute(
        "UPDATE documents SET content=?, metadata_json=?, word_count=?, indexed_at=NULL "
        "WHERE id=?",
        (new_content, json.dumps(meta), len(new_content.split()), concept_doc_id),
    )
    conn.commit()

    try:
        index_corpus(doc.get("corpus_id") or "")
    except Exception as e:
        logger.warning("index after recompile failed: %s", e)

    return {
        "status": "recompiled",
        "concept_id": concept_doc_id,
        "version": new_version,
        "previous_version": current_version,
        "source_doc_ids": merged_sources,
    }


def recompile_dirty_concepts(corpus_id: str | None = None, *, force: bool = False) -> dict:
    """Iterate concept docs and recompile any that are dirty (or all with force=True).

    When ``corpus_id`` is empty/None, scans every corpus. Returns a summary
    ``{recompiled, skipped, errors, concept_ids}`` suitable for CLI reporting.
    """
    conn = get_conn()
    if corpus_id:
        rows = conn.execute(
            "SELECT id FROM documents WHERE doc_type='concept' AND corpus_id=?",
            (corpus_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id FROM documents WHERE doc_type='concept'",
        ).fetchall()

    recompiled: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
    for r in rows:
        cid = r["id"]
        try:
            result = recompile_concept_if_dirty(cid, force=force)
            if result.get("status") == "recompiled":
                recompiled.append(cid)
            else:
                skipped.append(cid)
        except Exception as e:
            logger.warning("recompile failed for %s: %s", cid, e)
            errors.append({"concept_id": cid, "error": str(e)})
    return {
        "recompiled": recompiled,
        "skipped": skipped,
        "errors": errors,
        "total": len(rows),
    }


def refine_concept_note(concept_doc_id: str, instruction: str) -> dict:
    """Apply a natural-language edit instruction to a concept's compiled truth.

    Timeline is preserved byte-for-byte; only the compiled-truth section is
    rewritten. Snapshots prior version so refine history is diff-able.
    """
    from noosphere.core.ingest import get_document
    from noosphere.core.llm import call_llm as _call_llm

    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("instruction is required")

    doc = get_document(concept_doc_id)
    if not doc:
        raise ValueError(f"concept document not found: {concept_doc_id}")
    if (doc.get("doc_type") or "") != "concept":
        raise ValueError(f"not a concept document: {concept_doc_id}")

    try:
        meta = json.loads(doc.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        meta = {}
    current_version = int(meta.get("version", 1) or 1)

    compiled, timeline_lines = _parse_concept_content(doc.get("content") or "")

    _snapshot_concept_version(
        concept_doc_id,
        version=current_version,
        content=doc.get("content") or "",
        source_doc_ids=list(meta.get("source_document_ids") or []),
    )

    sys = (
        "You revise the 'compiled truth' section of a living knowledge-base concept note. "
        "Apply the user's revision instruction to the prior compiled truth. "
        "Preserve factual accuracy; do not invent facts not present in the prior text. "
        "Return ONLY the new compiled truth in Markdown — no '## Timeline' heading, no commentary. "
        "Use the same language as the prior text."
    )
    user = (
        f"Concept: {doc.get('title', '')}\n\n---\n\n"
        f"Prior compiled truth:\n\n{compiled or '(empty)'}\n\n---\n\n"
        f"Revision instruction:\n\n{instruction}\n\n---\n\n"
        "Rewrite the compiled truth now."
    )
    new_compiled = _call_llm(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    )
    if not new_compiled or new_compiled.startswith("No LLM provider"):
        raise ValueError(new_compiled or "LLM returned empty output")
    new_compiled = new_compiled.strip()

    new_content = _assemble_concept_content(new_compiled, timeline_lines)
    new_version = current_version + 1
    meta["version"] = new_version
    meta["last_compiled_at"] = datetime.now(timezone.utc).isoformat()
    meta["last_refine_instruction"] = instruction[:500]

    conn = get_conn()
    conn.execute(
        "UPDATE documents SET content=?, metadata_json=?, word_count=?, indexed_at=NULL "
        "WHERE id=?",
        (new_content, json.dumps(meta), len(new_content.split()), concept_doc_id),
    )
    conn.commit()

    try:
        index_corpus(doc.get("corpus_id") or "")
    except Exception as e:
        logger.warning("index after refine failed: %s", e)

    return {
        "status": "refined",
        "concept_id": concept_doc_id,
        "version": new_version,
        "previous_version": current_version,
        "compiled_truth": new_compiled,
    }


def _local_tag(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _parse_rss_atom(xml_bytes: bytes) -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom feed; return list of {title, link, summary, guid, published}."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"Invalid feed XML: {e}") from e

    items: list[dict[str, str]] = []
    root_name = _local_tag(root.tag)

    if root_name == "rss":
        channel = next((c for c in root if _local_tag(c.tag) == "channel"), None)
        if channel is None:
            return []
        for node in channel:
            if _local_tag(node.tag) != "item":
                continue
            title_el = next((x for x in node if _local_tag(x.tag) == "title"), None)
            link_el = next((x for x in node if _local_tag(x.tag) == "link"), None)
            desc_el = next((x for x in node if _local_tag(x.tag) == "description"), None)
            if desc_el is None:
                desc_el = next((x for x in node if _local_tag(x.tag) == "encoded"), None)
            guid_el = next((x for x in node if _local_tag(x.tag) == "guid"), None)
            pub_el = next((x for x in node if _local_tag(x.tag) == "pubDate"), None)
            title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
            link = (link_el.text or "").strip() if link_el is not None and link_el.text else ""
            summary = ""
            if desc_el is not None and desc_el.text:
                summary = desc_el.text.strip()
            guid = (guid_el.text or "").strip() if guid_el is not None and guid_el.text else link
            published = (pub_el.text or "").strip() if pub_el is not None and pub_el.text else ""
            if title or link:
                items.append({
                    "title": title or link or "Untitled",
                    "link": link,
                    "summary": summary[:80000],
                    "guid": guid or link,
                    "published": published,
                })
        return items

    if root_name == "feed":
        for entry in root.iter():
            if _local_tag(entry.tag) != "entry":
                continue
            title_el = next((x for x in entry if _local_tag(x.tag) == "title"), None)
            id_el = next((x for x in entry if _local_tag(x.tag) == "id"), None)
            summary_el = next((x for x in entry if _local_tag(x.tag) == "summary"), None)
            if summary_el is None:
                summary_el = next((x for x in entry if _local_tag(x.tag) == "content"), None)
            updated_el = next((x for x in entry if _local_tag(x.tag) == "updated"), None)
            if updated_el is None:
                updated_el = next((x for x in entry if _local_tag(x.tag) == "published"), None)
            link = ""
            for x in entry:
                if _local_tag(x.tag) == "link" and (x.get("href") or "").strip():
                    link = (x.get("href") or "").strip()
                    rel = (x.get("rel") or "alternate").lower()
                    if rel in ("alternate", "self", ""):
                        break
            title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
            guid = (id_el.text or "").strip() if id_el is not None and id_el.text else link
            summary = ""
            if summary_el is not None and summary_el.text:
                summary = summary_el.text.strip()
            published = (updated_el.text or "").strip() if updated_el is not None and updated_el.text else ""
            if title or link or guid:
                items.append({
                    "title": title or guid or "Untitled",
                    "link": link,
                    "summary": summary[:80000],
                    "guid": guid,
                    "published": published,
                })
        return items

    raise ValueError("Unsupported feed root element (expected rss or feed)")


def _feed_item_exists(corpus_id: str, guid: str, link: str) -> bool:
    conn = get_conn()
    rows = conn.execute(
        "SELECT metadata_json FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()
    for r in rows:
        try:
            meta = json.loads(r["metadata_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if meta.get("rss_guid") == guid or (link and meta.get("rss_link") == link):
            return True
    return False


def ingest_rss_feed(
    corpus_id: str,
    feed_url: str,
    *,
    max_items: int = 25,
    fetch_timeout: float = 30.0,
) -> dict[str, Any]:
    """Fetch RSS/Atom, ingest new entries (dedupe by guid/link). Returns counts + document ids."""
    resp = httpx.get(
        feed_url,
        follow_redirects=True,
        timeout=fetch_timeout,
        headers={"User-Agent": "Noosphere/0.1 (rss-ingestion)"},
    )
    resp.raise_for_status()
    entries = _parse_rss_atom(resp.content)
    ingested: list[dict] = []
    skipped = 0

    for entry in entries[:max_items]:
        guid = entry.get("guid") or entry.get("link") or ""
        link = entry.get("link") or ""
        if _feed_item_exists(corpus_id, guid, link):
            skipped += 1
            continue

        meta: dict[str, Any] = {
            "rss_guid": guid,
            "rss_link": link,
            "source_feed": feed_url,
            "rss_published": entry.get("published", ""),
        }
        title = entry.get("title") or "Feed item"

        doc: dict | None = None
        if link.startswith("http"):
            try:
                doc = ingest_url(corpus_id, link, doc_type="blog")
                # merge rss metadata into document — ingest_url sets source_url; add rss fields
                _merge_document_metadata(doc["id"], meta)
            except Exception as e:
                logger.warning("ingest_url failed for %s: %s", link, e)

        if doc is None:
            body = entry.get("summary") or ""
            if not body.strip():
                skipped += 1
                continue
            doc = ingest_text(
                corpus_id,
                title=title,
                content=f"# {title}\n\n{body}",
                doc_type="note",
                source_kind="external_public",
                date="",
                tags=["feed"],
                metadata=meta,
            )

        ingested.append(doc)

    index_stats: dict[str, Any] = {}
    if ingested:
        try:
            index_stats = index_corpus(corpus_id)
        except Exception as e:
            logger.warning("index after RSS ingest failed: %s", e)
            index_stats = {"error": str(e)}
        # Living-concept hook: link each new feed doc into matching concepts.
        for feed_doc in ingested:
            try:
                linked = _append_to_matching_concept_timelines(corpus_id, feed_doc["id"])
                if linked:
                    feed_doc["linked_concepts"] = linked
            except Exception as e:
                logger.warning(
                    "concept-timeline hook failed for feed doc %s: %s",
                    feed_doc.get("id"), e,
                )
        # Incremental re-index to pick up any concept timeline updates.
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("re-index after RSS hook failed: %s", e)

    return {
        "feed_url": feed_url,
        "fetched": len(entries),
        "ingested": len(ingested),
        "skipped": skipped,
        "documents": ingested,
        "index": index_stats,
    }


def _merge_document_metadata(doc_id: str, extra: dict) -> None:
    conn = get_conn()
    row = conn.execute("SELECT metadata_json FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        return
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    meta.update(extra)
    conn.execute(
        "UPDATE documents SET metadata_json=? WHERE id=?",
        (json.dumps(meta), doc_id),
    )
    conn.commit()


def save_capture(
    corpus_id: str,
    *,
    content: str,
    title: str = "",
    question: str = "",
    session_id: str = "",
    contributor_user_id: str | None = None,
) -> dict:
    """Persist a note from chat or manual capture; doc_type=capture with provenance metadata."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    safe_title = title.strip() or f"Capture {now}"
    meta: dict[str, Any] = {"capture_kind": "chat", "captured_at": now}
    if question:
        meta["source_question"] = question[:2000]
    if session_id:
        meta["chat_session_id"] = session_id

    body = content.strip()
    if not body:
        raise ValueError("content is required")

    doc = ingest_text(
        corpus_id,
        title=safe_title,
        content=body,
        doc_type="capture",
        source_kind="user_capture",
        tags=["capture"],
        metadata=meta,
        contributor_user_id=contributor_user_id,
    )
    try:
        index_corpus(corpus_id)
    except Exception as e:
        logger.warning("index after capture failed: %s", e)
    # Living-concept hook: link this capture into any matching concept's timeline.
    try:
        linked = _append_to_matching_concept_timelines(corpus_id, doc["id"])
        if linked:
            doc["linked_concepts"] = linked
    except Exception as e:
        logger.warning("concept-timeline hook failed for capture %s: %s", doc["id"], e)
    # Incremental re-index to pick up any concept content edits from the hook.
    try:
        index_corpus(corpus_id)
    except Exception as e:
        logger.warning("re-index after capture hook failed: %s", e)
    return doc


def compile_concept_note(
    corpus_id: str,
    topic: str,
    *,
    top_k: int = 10,
    max_output_words: int = 1200,
) -> dict:
    """LLM-synthesized concept doc from retrieved passages (initial compile step).

    Emits the living-concept format: compiled truth above ``## Timeline``, then
    an initial timeline entry per source doc. Subsequent ingests append to the
    timeline via the hook; ``recompile_concept_if_dirty`` rewrites the compiled
    truth without touching the timeline.
    """
    from noosphere.core.llm import call_llm as _call_llm
    from noosphere.core.ingest import get_document

    retrieval = search_corpus(corpus_id, topic, top_k=top_k)
    chunks = retrieval.get("results", [])
    if not chunks:
        raise ValueError("No sources found for this topic — add documents or broaden the topic.")

    source_ids: list[str] = []
    parts: list[str] = []
    for i, ch in enumerate(chunks):
        cite = ch.get("citation", {})
        did = cite.get("document_id", "")
        if did and did not in source_ids:
            source_ids.append(did)
        label = cite.get("document_title", f"Source {i + 1}")
        parts.append(f"### [{label}]\n{ch.get('text', '')}")

    context = "\n\n---\n\n".join(parts)
    sys = (
        "You write the 'compiled truth' section of a living knowledge-base concept note. "
        "Synthesize the excerpts into one note: Summary, Key points (bullets), "
        "Connections (how ideas relate), Open questions / gaps, Sources (list document titles). "
        "Do not invent facts not supported by the excerpts. Use the same language as the excerpts. "
        "Do NOT emit a '## Timeline' heading — the system appends it automatically."
    )
    user = (
        f"Topic / focus:\n{topic}\n\n---\n\nExcerpts:\n\n{context}\n\n"
        f"Keep under ~{max_output_words} words."
    )
    text = _call_llm([{"role": "system", "content": sys}, {"role": "user", "content": user}])
    if not text or text.startswith("No LLM provider"):
        raise ValueError(text or "LLM returned empty output")

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    timeline_lines: list[str] = []
    for sid in source_ids[:20]:
        sdoc = get_document(sid)
        stitle = ((sdoc.get("title") if sdoc else None) or sid).replace("\n", " ")[:200]
        timeline_lines.append(f"- {date_str} — initial compile: {stitle} [id={sid}]")
    body = _assemble_concept_content(text.strip(), timeline_lines)

    safe_topic = re.sub(r"[^\w\s\-]", "", topic)[:80].strip() or "Concept"
    title = f"Concept: {safe_topic}"
    meta = {
        "compiled_from_query": topic[:500],
        "source_document_ids": source_ids[:50],
        "compile_kind": "concept_note",
        "version": 1,
        "timeline_dirty": False,
        "pending_changes": 0,
        "last_compiled_at": datetime.now(timezone.utc).isoformat(),
    }
    doc = ingest_text(
        corpus_id,
        title=title,
        content=body,
        doc_type="concept",
        source_kind="user_original",
        tags=["concept", "compiled"],
        metadata=meta,
    )
    try:
        index_corpus(corpus_id)
    except Exception as e:
        logger.warning("index after compile failed: %s", e)
    return doc


def ingest_urls_bulk(
    corpus_id: str,
    urls: list[str],
    *,
    doc_type: str = "blog",
    source_kind: str | None = None,
) -> dict[str, Any]:
    """Ingest multiple HTTP URLs (lower-friction batch inflow)."""
    results: list[dict] = []
    errors: list[dict] = []
    for url in urls:
        u = (url or "").strip()
        if not u.startswith("http"):
            errors.append({"url": url, "error": "invalid URL"})
            continue
        try:
            results.append(ingest_url(corpus_id, u, doc_type=doc_type, source_kind=source_kind))
        except Exception as e:
            errors.append({"url": u, "error": str(e)})
    idx: dict[str, Any] = {}
    if results:
        try:
            idx = index_corpus(corpus_id)
        except Exception as e:
            idx = {"error": str(e)}
        for url_doc in results:
            try:
                linked = _append_to_matching_concept_timelines(corpus_id, url_doc["id"])
                if linked:
                    url_doc["linked_concepts"] = linked
            except Exception as e:
                logger.warning(
                    "concept-timeline hook failed for URL doc %s: %s",
                    url_doc.get("id"), e,
                )
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("re-index after URL bulk hook failed: %s", e)
    return {"ingested": len(results), "failed": len(errors), "documents": results, "errors": errors, "index": idx}


def corpus_knowledge_health(corpus_id: str) -> dict[str, Any]:
    """Lint-style signals: missing index coverage, rough link hygiene."""
    conn = get_conn()
    corpus = conn.execute("SELECT * FROM corpora WHERE id=?", (corpus_id,)).fetchone()
    if not corpus:
        raise ValueError("corpus not found")

    doc_rows = conn.execute(
        "SELECT id, title, content, indexed_at, created_at FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()

    chunk_docs = {
        r["document_id"]
        for r in conn.execute(
            "SELECT DISTINCT document_id FROM chunks WHERE corpus_id=?",
            (corpus_id,),
        ).fetchall()
    }

    without_chunks: list[dict] = []
    empty_link_hits = 0
    for r in doc_rows:
        if r["id"] not in chunk_docs:
            without_chunks.append({"id": r["id"], "title": r["title"]})
        content = r["content"] or ""
        empty_link_hits += len(re.findall(r"\]\(\s*\)", content))
        empty_link_hits += len(re.findall(r"\]\(\s*#?\s*\)", content))

    threshold = int(corpus["stale_threshold_days"] or 365)
    stale_candidates: list[dict] = []
    now = datetime.now(timezone.utc)
    for r in doc_rows:
        created = r["created_at"] or ""
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if (now - dt).days > threshold:
                stale_candidates.append({"id": r["id"], "title": r["title"], "created_at": created})
        except (ValueError, TypeError):
            continue

    capture_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE corpus_id=? AND doc_type='capture'",
        (corpus_id,),
    ).fetchone()["c"]
    concept_count = conn.execute(
        "SELECT COUNT(*) as c FROM documents WHERE corpus_id=? AND doc_type='concept'",
        (corpus_id,),
    ).fetchone()["c"]

    return {
        "corpus_id": corpus_id,
        "document_count": len(doc_rows),
        "documents_without_chunks": without_chunks,
        "documents_without_chunks_count": len(without_chunks),
        "suspected_empty_markdown_links": empty_link_hits,
        "stale_threshold_days": threshold,
        "documents_older_than_threshold": stale_candidates[:50],
        "documents_older_than_threshold_count": len(stale_candidates),
        "capture_documents": int(capture_count),
        "concept_documents": int(concept_count),
    }


def run_corpus_maintain(corpus_id: str, *, force_reindex: bool = False) -> dict[str, Any]:
    """Re-run indexing (repairs chunk/FTS drift); optional full force."""
    return index_corpus(corpus_id, force=force_reindex)
