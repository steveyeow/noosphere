"""Entity extraction + storage for knowledge bases.

Entities are the people, companies, concepts, and places mentioned across a
corpus. Every doc can have:
  - an author_entity_id (who wrote / produced it) — single FK on documents
  - participant_entity_ids — multi-party content like meeting transcripts
  - mentioned_entity_ids — references; stored in documents.metadata_json

Entity pages (Phase 0.6) aggregate all three relationships to give a
GBrain/Karpathy-style "one page per person / one page per company" view.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from noosphere.core.db import get_conn

logger = logging.getLogger(__name__)

VALID_KINDS = {"person", "company", "concept", "place"}
_EXTRACTION_MAX_CHARS = 3000
_MIN_WORDS_FOR_EXTRACTION = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_name(name: str) -> str:
    """Normalize a canonical_name for dedup: strip, collapse whitespace.
    Kept case-sensitive — "AI" and "ai" are different, but "Paul Graham"
    matches " paul graham ".
    """
    return re.sub(r"\s+", " ", (name or "").strip())


# ── CRUD ──────────────────────────────────────────────────────────────


def upsert_entity(
    corpus_id: str,
    kind: str,
    canonical_name: str,
    *,
    aliases: list[str] | None = None,
    description: str = "",
    metadata: dict | None = None,
) -> str | None:
    """Insert a new entity or return the id of an existing match.

    Matching key: (corpus_id, kind, normalized canonical_name) — case-insensitive.
    If found, aliases from the input are merged into the existing entity.
    Returns the entity_id, or None on invalid input.
    """
    if kind not in VALID_KINDS:
        return None
    name = _normalize_name(canonical_name)
    if not name:
        return None

    conn = get_conn()
    # Case-insensitive match on canonical_name within (corpus_id, kind).
    row = conn.execute(
        "SELECT id, aliases FROM entities "
        "WHERE corpus_id=? AND kind=? AND LOWER(canonical_name)=LOWER(?)",
        (corpus_id, kind, name),
    ).fetchone()

    now = _now()
    if row:
        eid = row["id"]
        if aliases:
            try:
                existing = json.loads(row["aliases"] or "[]")
            except (json.JSONDecodeError, TypeError):
                existing = []
            merged = list(dict.fromkeys([*existing, *aliases]))  # preserve order, dedupe
            if merged != existing:
                conn.execute(
                    "UPDATE entities SET aliases=?, updated_at=? WHERE id=?",
                    (json.dumps(merged), now, eid),
                )
                conn.commit()
        return eid

    eid = uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO entities (id, corpus_id, kind, canonical_name, aliases, "
        "description, metadata_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            eid, corpus_id, kind, name,
            json.dumps(aliases or []),
            description or "",
            json.dumps(metadata or {}),
            now, now,
        ),
    )
    conn.commit()
    return eid


def get_entity(entity_id: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM entities WHERE id=?", (entity_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_entity_with_related_docs(entity_id: str) -> dict | None:
    """Entity detail + three buckets of related docs (one page per entity).

    Buckets mirror the three linking patterns set during ingest/enrichment:
      - authored_by: documents.author_entity_id == entity_id
      - participated: entity_id appears in documents.participant_entity_ids
      - mentioned_in: entity_id appears in metadata_json.mentioned_entity_ids

    A doc that qualifies under multiple buckets only appears in the strongest
    one (authored > participated > mentioned) to avoid duplicate rendering.
    """
    ent = get_entity(entity_id)
    if not ent:
        return None

    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, doc_type, date, source_kind, author_entity_id, "
        "participant_entity_ids, metadata_json, word_count, created_at "
        "FROM documents WHERE corpus_id=? ORDER BY created_at DESC",
        (ent["corpus_id"],),
    ).fetchall()

    authored: list[dict] = []
    participated: list[dict] = []
    mentioned: list[dict] = []

    for r in rows:
        doc_summary = {
            "id": r["id"],
            "title": r["title"],
            "doc_type": r["doc_type"],
            "date": r["date"],
            "source_kind": r["source_kind"] or "user_original",
            "word_count": r["word_count"] or 0,
            "created_at": r["created_at"],
        }
        if r["author_entity_id"] == entity_id:
            authored.append(doc_summary)
            continue
        try:
            pids = json.loads(r["participant_entity_ids"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pids = []
        if entity_id in pids:
            participated.append(doc_summary)
            continue
        try:
            meta = json.loads(r["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        if entity_id in (meta.get("mentioned_entity_ids") or []):
            mentioned.append(doc_summary)

    ent["authored_by"] = authored
    ent["participated"] = participated
    ent["mentioned_in"] = mentioned
    ent["doc_count"] = len(authored) + len(participated) + len(mentioned)
    return ent


def list_entities(corpus_id: str, *, kind: str | None = None) -> list[dict]:
    """List entities in a corpus, optionally filtered by kind.

    Returns each entity annotated with mention_count (docs that reference it
    via author_entity_id, participant_entity_ids, or metadata_json mentions).
    """
    conn = get_conn()
    if kind:
        rows = conn.execute(
            "SELECT * FROM entities WHERE corpus_id=? AND kind=? ORDER BY canonical_name",
            (corpus_id, kind),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM entities WHERE corpus_id=? ORDER BY kind, canonical_name",
            (corpus_id,),
        ).fetchall()

    entities = [_row_to_dict(r) for r in rows]
    if not entities:
        return []

    entity_ids = {e["id"] for e in entities}
    mention_counts: dict[str, int] = {eid: 0 for eid in entity_ids}

    # Authored + participants (structured columns)
    doc_rows = conn.execute(
        "SELECT author_entity_id, participant_entity_ids, metadata_json "
        "FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()
    for d in doc_rows:
        seen_for_doc: set[str] = set()
        aid = d["author_entity_id"]
        if aid and aid in entity_ids:
            seen_for_doc.add(aid)
        try:
            pids = json.loads(d["participant_entity_ids"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pids = []
        for p in pids:
            if p in entity_ids:
                seen_for_doc.add(p)
        try:
            meta = json.loads(d["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        for m in meta.get("mentioned_entity_ids", []) or []:
            if m in entity_ids:
                seen_for_doc.add(m)
        for eid in seen_for_doc:
            mention_counts[eid] = mention_counts.get(eid, 0) + 1

    for e in entities:
        e["mention_count"] = mention_counts.get(e["id"], 0)
    return entities


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("aliases",):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                d[key] = []
    if "metadata_json" in d and isinstance(d["metadata_json"], str):
        try:
            d["metadata"] = json.loads(d["metadata_json"])
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
    return d


# ── HTML author detection (free — no LLM) ────────────────────────────


_AUTHOR_META_PATTERNS = [
    re.compile(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+property=["\']article:author["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+property=["\']og:article:author["\']\s+content=["\']([^"\']+)["\']', re.I),
    re.compile(r'<meta\s+name=["\']twitter:creator["\']\s+content=["\']@?([^"\']+)["\']', re.I),
]


def detect_html_author(html: str) -> str | None:
    """Best-effort author extraction from HTML <meta> tags. Returns None if not found."""
    if not html:
        return None
    for pat in _AUTHOR_META_PATTERNS:
        m = pat.search(html)
        if m:
            name = _normalize_name(m.group(1))
            if name:
                return name
    return None


# ── LLM-based extraction ─────────────────────────────────────────────


def _parse_llm_entities_json(raw: str) -> list[dict]:
    """Parse LLM JSON output defensively. Returns [] on failure."""
    if not raw:
        return []
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        entities = data.get("entities", [])
    elif isinstance(data, list):
        entities = data
    else:
        return []
    out: list[dict] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        name = _normalize_name(e.get("name", "") or e.get("canonical_name", ""))
        kind = (e.get("kind") or e.get("type") or "").strip().lower()
        if not name or kind not in VALID_KINDS:
            continue
        out.append({"kind": kind, "canonical_name": name})
    return out


def extract_entities_from_text(text: str) -> list[dict]:
    """LLM-call to extract named entities from a text excerpt.

    Returns list of {kind, canonical_name}. Empty list on LLM unavailable / failure.
    """
    from noosphere.core.llm import call_llm

    content = (text or "")[:_EXTRACTION_MAX_CHARS]
    if len(content.split()) < _MIN_WORDS_FOR_EXTRACTION:
        return []

    prompt_text = (
        "Extract named entities from the text. Respond with JSON only, no markdown fences:\n"
        '{"entities": [{"name": "Full Name", "kind": "person|company|concept|place"}]}\n\n'
        "Rules:\n"
        "- Only include entities that are NAMED (proper nouns) or well-defined concepts.\n"
        "- Merge variants: use the canonical full name (e.g. 'Paul Graham' not 'pg').\n"
        "- Limit to the most important 8-12 entities.\n"
        "- Omit generic terms, months, colors, numbers.\n\n"
        f"Text:\n{content}"
    )
    messages = [
        {"role": "system", "content": "You extract structured entity data from text. Respond only with valid JSON."},
        {"role": "user", "content": prompt_text},
    ]
    try:
        raw = call_llm(messages)
    except Exception as e:
        logger.warning("Entity extraction LLM call failed: %s", e)
        return []
    if not raw or raw.startswith("No LLM provider"):
        return []
    return _parse_llm_entities_json(raw)


# ── Document enrichment ──────────────────────────────────────────────


def enrich_document(doc_id: str, *, use_llm: bool = True) -> dict | None:
    """Extract entities from a document, upsert them, link as mentions.

    Returns summary dict or None if the document doesn't exist.
    Idempotent-ish: merges new entity ids into existing mentioned_entity_ids.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id, corpus_id, content, metadata_json FROM documents WHERE id=?",
        (doc_id,),
    ).fetchone()
    if not row:
        return None

    corpus_id = row["corpus_id"]
    content = row["content"] or ""

    extracted: list[dict] = []
    if use_llm:
        extracted = extract_entities_from_text(content)

    entity_ids: list[str] = []
    for ent in extracted:
        eid = upsert_entity(corpus_id, ent["kind"], ent["canonical_name"])
        if eid:
            entity_ids.append(eid)

    # Merge into metadata_json.mentioned_entity_ids (preserve pre-existing)
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    existing_mentions = meta.get("mentioned_entity_ids") or []
    merged = list(dict.fromkeys([*existing_mentions, *entity_ids]))
    meta["mentioned_entity_ids"] = merged
    meta["enriched_at"] = _now()

    conn.execute(
        "UPDATE documents SET metadata_json=? WHERE id=?",
        (json.dumps(meta), doc_id),
    )
    conn.commit()

    return {
        "document_id": doc_id,
        "entities_extracted": len(extracted),
        "mentioned_entity_ids": merged,
        "new_mentions": len(set(entity_ids) - set(existing_mentions)),
    }


def compile_entity_note(entity_id: str, *, max_docs: int = 20, max_chars_per_doc: int = 1500) -> dict | None:
    """LLM-synthesize a 'compiled truth' summary about an entity from all its
    related documents.

    Writes the output to entities.description (overwrites prior compile).
    Returns {entity_id, compiled_text, source_doc_count} or None if the entity
    doesn't exist / has no related docs / LLM unavailable.
    """
    from noosphere.core.llm import call_llm

    ent = get_entity_with_related_docs(entity_id)
    if not ent:
        return None

    conn = get_conn()
    # Assemble passages — prioritize authored, then participated, then mentioned.
    related = [*ent.get("authored_by", []), *ent.get("participated", []), *ent.get("mentioned_in", [])]
    if not related:
        return None

    parts: list[str] = []
    source_ids: list[str] = []
    for d in related[:max_docs]:
        row = conn.execute("SELECT content FROM documents WHERE id=?", (d["id"],)).fetchone()
        if not row or not row["content"]:
            continue
        body = row["content"].strip()[:max_chars_per_doc]
        source_ids.append(d["id"])
        parts.append(f"### [{d['title']}]\n{body}")

    if not parts:
        return None

    context = "\n\n---\n\n".join(parts)
    name = ent["canonical_name"]
    kind = ent["kind"]
    sys = (
        f"You are writing a concise factual profile of a {kind} based on the provided excerpts from a personal knowledge base. "
        "Use only information grounded in the excerpts. Include: who/what they are, what they do, "
        "key relationships and themes, and anything distinctive or recurring. "
        "Do not invent facts. Use the same language as the excerpts. Keep under 250 words."
    )
    user = f"Entity: {name} ({kind})\n\nExcerpts:\n\n{context}"
    try:
        text = call_llm([{"role": "system", "content": sys}, {"role": "user", "content": user}])
    except Exception as e:
        logger.warning("compile_entity_note LLM call failed for %s: %s", entity_id, e)
        return None
    if not text or text.startswith("No LLM provider"):
        return None

    compiled = text.strip()
    try:
        meta = json.loads((ent.get("metadata_json") or "{}") if isinstance(ent.get("metadata_json"), str) else json.dumps(ent.get("metadata") or {}))
    except (json.JSONDecodeError, TypeError):
        meta = {}
    meta["compiled_at"] = _now()
    meta["compiled_from_doc_ids"] = source_ids
    conn.execute(
        "UPDATE entities SET description=?, metadata_json=?, updated_at=? WHERE id=?",
        (compiled, json.dumps(meta), _now(), entity_id),
    )
    conn.commit()
    return {"entity_id": entity_id, "compiled_text": compiled, "source_doc_count": len(source_ids)}


def enrich_corpus(corpus_id: str, *, only_unenriched: bool = True, limit: int = 50) -> dict:
    """Run entity extraction across documents in a corpus.

    only_unenriched: skip docs that already have enriched_at in metadata.
    limit: cap per invocation so the UI request doesn't hang forever;
           callers can re-invoke until "remaining" reaches 0.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, metadata_json FROM documents WHERE corpus_id=?",
        (corpus_id,),
    ).fetchall()

    targets: list[str] = []
    for r in rows:
        if only_unenriched:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                meta = {}
            if meta.get("enriched_at"):
                continue
        targets.append(r["id"])

    remaining_after = max(0, len(targets) - limit)
    batch = targets[:limit]

    enriched_count = 0
    total_new_entities = 0
    for did in batch:
        result = enrich_document(did)
        if result:
            enriched_count += 1
            total_new_entities += result.get("new_mentions", 0)

    return {
        "corpus_id": corpus_id,
        "enriched": enriched_count,
        "remaining": remaining_after,
        "new_mentions_total": total_new_entities,
    }
