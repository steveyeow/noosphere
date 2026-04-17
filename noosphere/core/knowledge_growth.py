"""Knowledge growth: capture from chat, RSS inflow, LLM synthesis, corpus health.

Bridges gaps vs personal LLM-wiki workflows (incremental compile, feeds, chat→KB).
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from noosphere.core.db import get_conn
from noosphere.core.ingest import ingest_text, ingest_url
from noosphere.core.indexer import index_corpus
from noosphere.core.retrieval import search_corpus

logger = logging.getLogger(__name__)


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


def evaluate_and_auto_capture(
    corpus_id: str,
    user_message: str,
    assistant_response: str,
    citations: list[dict],
    session_id: str = "",
) -> dict | None:
    """Auto-capture qualifying chat responses as corpus documents.

    Heuristic: response must be substantive (>=50 words), draw from multiple
    sources (>=2 citations), and not be a refusal.
    """
    words = assistant_response.split()
    if len(words) < 50:
        return None
    if len(citations) < 2:
        return None
    first_50_chars = assistant_response[:50]
    if "I don't" in first_50_chars or "I cannot" in first_50_chars:
        return None

    title = user_message[:80].strip() or "Auto-capture"
    try:
        doc = save_capture(
            corpus_id,
            content=assistant_response,
            title=f"[Auto] {title}",
            question=user_message,
            session_id=session_id,
        )
        # Overwrite capture metadata to mark as auto
        _merge_document_metadata(doc["id"], {"capture_kind": "auto"})
        # Add auto-capture tag
        conn = get_conn()
        row = conn.execute("SELECT tags FROM documents WHERE id=?", (doc["id"],)).fetchone()
        if row:
            try:
                tags = json.loads(row["tags"] or "[]")
            except json.JSONDecodeError:
                tags = []
            if "auto-capture" not in tags:
                tags.append("auto-capture")
                conn.execute("UPDATE documents SET tags=? WHERE id=?", (json.dumps(tags), doc["id"]))
                conn.commit()
        logger.info("Auto-captured chat response as document %s in corpus %s", doc["id"], corpus_id)
        return doc
    except Exception as e:
        logger.warning("Auto-capture failed for corpus %s: %s", corpus_id, e)
        return None


def save_capture(
    corpus_id: str,
    *,
    content: str,
    title: str = "",
    question: str = "",
    session_id: str = "",
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
        tags=["capture"],
        metadata=meta,
    )
    try:
        index_corpus(corpus_id)
    except Exception as e:
        logger.warning("index after capture failed: %s", e)
    return doc


def compile_concept_note(
    corpus_id: str,
    topic: str,
    *,
    top_k: int = 10,
    max_output_words: int = 1200,
) -> dict:
    """LLM-synthesized concept doc from retrieved passages (fusion / compile step)."""
    from noosphere.core.llm import call_llm as _call_llm

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
        "You write structured Markdown concept notes for a knowledge base. "
        "Synthesize the excerpts into one note: Summary, Key points (bullets), "
        "Connections (how ideas relate), Open questions / gaps, Sources (list document titles). "
        "Do not invent facts not supported by the excerpts. Use the same language as the excerpts."
    )
    user = (
        f"Topic / focus:\n{topic}\n\n---\n\nExcerpts:\n\n{context}\n\n"
        f"Keep under ~{max_output_words} words."
    )
    text = _call_llm([{"role": "system", "content": sys}, {"role": "user", "content": user}])
    if not text or text.startswith("No LLM provider"):
        raise ValueError(text or "LLM returned empty output")

    safe_topic = re.sub(r"[^\w\s\-]", "", topic)[:80].strip() or "Concept"
    title = f"Concept: {safe_topic}"
    meta = {
        "compiled_from_query": topic[:500],
        "source_document_ids": source_ids[:50],
        "compile_kind": "concept_note",
    }
    doc = ingest_text(
        corpus_id,
        title=title,
        content=text,
        doc_type="concept",
        tags=["concept", "compiled"],
        metadata=meta,
    )
    try:
        index_corpus(corpus_id)
    except Exception as e:
        logger.warning("index after compile failed: %s", e)
    return doc


def ingest_urls_bulk(corpus_id: str, urls: list[str], *, doc_type: str = "blog") -> dict[str, Any]:
    """Ingest multiple HTTP URLs (lower-friction batch inflow)."""
    results: list[dict] = []
    errors: list[dict] = []
    for url in urls:
        u = (url or "").strip()
        if not u.startswith("http"):
            errors.append({"url": url, "error": "invalid URL"})
            continue
        try:
            results.append(ingest_url(corpus_id, u, doc_type=doc_type))
        except Exception as e:
            errors.append({"url": u, "error": str(e)})
    idx: dict[str, Any] = {}
    if results:
        try:
            idx = index_corpus(corpus_id)
        except Exception as e:
            idx = {"error": str(e)}
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


def extract_and_tag(document_id: str) -> dict[str, Any] | None:
    """Extract entities, tags, and summary from a document using LLM.

    Updates the document's metadata_json with entities, auto_summary,
    and merges suggested tags into the document's tags array.
    """
    from noosphere.core.llm import call_llm

    conn = get_conn()
    row = conn.execute("SELECT id, content, tags, metadata_json FROM documents WHERE id=?", (document_id,)).fetchone()
    if not row:
        return None

    content = (row["content"] or "")[:3000]
    if len(content.split()) < 20:
        return None  # Too short to extract anything meaningful

    prompt_text = (
        "Analyze this text and respond in JSON only (no markdown fences):\n"
        '{"entities": [{"name": "...", "type": "person|company|concept|place"}], '
        '"tags": ["tag1", "tag2", "tag3"], '
        '"summary": "One sentence summary."}\n\n'
        f"Text: {content}"
    )
    messages = [
        {"role": "system", "content": "You extract structured metadata from text. Respond only with valid JSON."},
        {"role": "user", "content": prompt_text},
    ]

    try:
        raw = call_llm(messages)
    except Exception as e:
        logger.warning("LLM call failed for entity extraction on doc %s: %s", document_id, e)
        return None

    if not raw or raw.startswith("No LLM provider"):
        return None

    # Parse JSON from LLM response (strip markdown fences if present)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse entity extraction JSON for doc %s", document_id)
        return None

    entities = data.get("entities", [])
    suggested_tags = data.get("tags", [])
    summary = data.get("summary", "")

    # Update metadata
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    meta["entities"] = entities
    if summary:
        meta["auto_summary"] = summary

    # Merge tags
    try:
        existing_tags = json.loads(row["tags"] or "[]")
    except json.JSONDecodeError:
        existing_tags = []
    for tag in suggested_tags:
        tag_lower = tag.lower().strip()
        if tag_lower and tag_lower not in [t.lower() for t in existing_tags]:
            existing_tags.append(tag_lower)

    conn.execute(
        "UPDATE documents SET metadata_json=?, tags=? WHERE id=?",
        (json.dumps(meta), json.dumps(existing_tags), document_id),
    )
    conn.commit()

    return {
        "document_id": document_id,
        "entities": entities,
        "tags": existing_tags,
        "summary": summary,
    }


def _entity_extraction_hook(doc: dict):
    """Post-ingest hook: run entity extraction on newly ingested documents.

    Skips in cloud mode (LLM cost is metered per-user, background extraction
    would bypass quota). Self-hosted: runs only if an LLM API key is configured.
    Skips captures and concepts (already processed content) and very short documents.
    """
    from noosphere.core.config import ENABLE_CLOUD, GEMINI_API_KEY, OPENAI_API_KEY
    if ENABLE_CLOUD:
        return  # Cloud users trigger extraction manually within their quota
    if not (GEMINI_API_KEY or OPENAI_API_KEY):
        return  # No LLM configured
    if doc.get("doc_type") in ("capture", "concept"):
        return
    if (doc.get("word_count") or 0) < 30:
        return
    try:
        result = extract_and_tag(doc["id"])
        if result:
            logger.info("Auto-extracted entities for doc %s (%d entities)", doc.get("id"), len(result.get("entities", [])))
    except Exception as e:
        logger.debug("Entity extraction hook skipped for %s: %s", doc.get("id"), e)


def register_entity_extraction_hook():
    """Register the entity extraction post-ingest hook. Call once at startup."""
    from noosphere.core.ingest import register_post_ingest_hook
    register_post_ingest_hook(_entity_extraction_hook)


def enrich_extract_backfill(corpus_id: str, *, limit: int = 10) -> dict[str, Any]:
    """Batch entity extraction for documents that haven't been processed yet."""
    conn = get_conn()
    docs = conn.execute(
        "SELECT id, metadata_json FROM documents WHERE corpus_id=? ORDER BY created_at DESC",
        (corpus_id,),
    ).fetchall()

    extracted = 0
    skipped = 0
    for doc in docs:
        if extracted >= limit:
            break
        try:
            meta = json.loads(doc["metadata_json"] or "{}")
        except json.JSONDecodeError:
            meta = {}
        if "entities" in meta:
            skipped += 1
            continue
        result = extract_and_tag(doc["id"])
        if result:
            extracted += 1
        else:
            skipped += 1

    return {"extracted": extracted, "skipped": skipped}


def enrich_auto_compile(corpus_id: str, *, limit: int = 2) -> dict[str, Any]:
    """Find high-frequency entities and compile concept notes for them.

    Scans all documents for entity mentions, finds entities mentioned 3+ times
    that don't have a concept note yet, and compiles one.
    """
    conn = get_conn()
    docs = conn.execute(
        "SELECT id, metadata_json FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()

    # Count entity mentions across all documents
    entity_counts: dict[str, int] = {}
    for doc in docs:
        try:
            meta = json.loads(doc["metadata_json"] or "{}")
        except json.JSONDecodeError:
            continue
        for ent in meta.get("entities", []):
            name = ent.get("name", "").strip()
            if name:
                entity_counts[name] = entity_counts.get(name, 0) + 1

    # Find existing concept notes
    concept_rows = conn.execute(
        "SELECT title FROM documents WHERE corpus_id=? AND doc_type='concept'",
        (corpus_id,),
    ).fetchall()
    existing_concepts = {r["title"].lower() for r in concept_rows}

    # Candidates: mentioned 3+ times, no concept note yet
    candidates = [
        name for name, count in sorted(entity_counts.items(), key=lambda x: -x[1])
        if count >= 3 and f"concept: {name.lower()}" not in existing_concepts
    ]

    compiled = []
    for topic in candidates[:limit]:
        try:
            doc = compile_concept_note(corpus_id, topic, top_k=8)
            compiled.append({"topic": topic, "document_id": doc["id"]})
        except Exception as e:
            logger.warning("Auto-compile failed for '%s': %s", topic, e)

    return {"candidates_found": len(candidates), "compiled": compiled}


def run_enrich_cycle(corpus_id: str) -> dict[str, Any]:
    """Orchestrate a full enrichment cycle: extract, compile, health check."""
    results: dict[str, Any] = {"corpus_id": corpus_id}

    # Phase 1: Entity extraction backfill
    try:
        results["entity_backfill"] = enrich_extract_backfill(corpus_id, limit=10)
    except Exception as e:
        results["entity_backfill"] = {"error": str(e)}

    # Phase 2: Auto-compile concept notes
    try:
        results["auto_compile"] = enrich_auto_compile(corpus_id, limit=2)
    except Exception as e:
        results["auto_compile"] = {"error": str(e)}

    # Phase 3: Health check
    try:
        results["health"] = corpus_knowledge_health(corpus_id)
    except Exception as e:
        results["health"] = {"error": str(e)}

    return results


def run_corpus_maintain(corpus_id: str, *, force_reindex: bool = False) -> dict[str, Any]:
    """Re-run indexing (repairs chunk/FTS drift); optional full force."""
    return index_corpus(corpus_id, force=force_reindex)
