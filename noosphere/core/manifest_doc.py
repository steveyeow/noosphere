"""Manifest document — the KB's README.md.

Every corpus has a machine-readable manifest (task_types, samples,
description, calibration_policy) that lives on the corpus row and is
served to discovery agents via /describe.

This module materializes that manifest as a real markdown document —
`doc_type='manifest'` — pinned as the first item in the Wiki section.
The document is auto-rendered from the corpus's structured fields; DB
columns remain the source of truth, the document is the human-readable
view.

Why a real doc instead of a virtual card:
- Matches creator mental model ("manifest is the KB's README.md")
- Stored, exportable, indexable — the full "identity file"
- Survives theme / client changes (plain markdown)
- Gives a visible surface where future freeform body editing can land
  without moving the rendered output anywhere else

Why the DB columns are still source of truth:
- task_types enum + samples structure need type-safe edits; a single
  markdown parser would fight the LLM-driven auto-apply flow
- /describe stays a simple SELECT from the corpus row; the doc is a
  SELECT on documents and gets regenerated on field change

Flow:
- New corpus: `ensure_manifest_doc(corpus_id)` is called after
  `manifest_autofill.auto_apply_if_missing` so the doc has real content
  (not an empty-stub manifest).
- Existing corpus: lazy — `ensure_manifest_doc` is called from the
  corpus-detail load path; if no manifest doc exists it's created now.
- Field edit: `refresh_manifest_doc(corpus_id)` rewrites the doc's
  content column in place (same doc id). Called from corpus PATCH and
  from manifest_autofill.apply_manifest_updates.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from noosphere.core.db import get_conn

MANIFEST_DOC_TYPE = "manifest"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_list(val, default=None):
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val:
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return default if default is not None else []


def _coerce_dict(val, default=None):
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val:
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return default if default is not None else {}


def render_manifest_markdown(corpus: dict) -> str:
    """Render a corpus's manifest fields as a markdown document.

    Takes the raw corpus row (from get_corpus) — handles JSON-encoded
    list/dict fields defensively so it works whether called from ORM
    code (already decoded) or raw SQL results.
    """
    name = corpus.get("name") or "Untitled"
    description = (corpus.get("description") or "").strip()
    access_level = corpus.get("access_level") or "public"
    tags = _coerce_list(corpus.get("tags"))
    task_types = _coerce_list(corpus.get("task_types"))
    samples = _coerce_list(corpus.get("samples"))
    calibration = _coerce_dict(corpus.get("calibration_policy"))
    autonomy_level = int(corpus.get("autonomy_level") or 0)

    lines: list[str] = []

    # Title
    lines.append(f"# {name}")
    lines.append("")

    # Description
    if description:
        lines.append(description)
    else:
        lines.append("_No description yet._")
    lines.append("")

    # Tags (if any)
    if tags:
        lines.append("**Tags:** " + ", ".join(f"`{t}`" for t in tags))
        lines.append("")

    # Answers — what this KB handles
    lines.append("## What this KB answers")
    lines.append("")
    if task_types:
        for t in task_types:
            lines.append(f"- `{t}`")
    else:
        lines.append("_Auto-deriving from content — propose some task types by running compile or adding documents._")
    lines.append("")

    # Sample Q&A — agent-facing examples
    if samples:
        lines.append("## Sample questions this KB answers well")
        lines.append("")
        for s in samples:
            if not isinstance(s, dict):
                continue
            q = (s.get("question") or "").strip()
            a = (s.get("answer_preview") or "").strip()
            if not q:
                continue
            lines.append(f"**Q:** {q}")
            if a:
                lines.append(f"**A:** {a}")
            lines.append("")

    # Trust signals
    lines.append("## Trust signals")
    lines.append("")
    if calibration and calibration.get("reports_confidence"):
        source = calibration.get("confidence_source") or "self"
        label = "third-party calibrated" if source == "third_party" else "self-assessed"
        lines.append(f"- **Confidence:** {label}")
    else:
        lines.append("- **Confidence:** not reported")
    # Access / licensing terms
    lic_map = {
        "public": "Free for any agent to query",
        "token": "Free after you issue a token",
        "paid": "Agents pay per query",
        "private": "Not licensed — private",
    }
    lines.append(f"- **Licensing:** {lic_map.get(access_level, lic_map['public'])}")
    lines.append("")

    # Autonomy
    autonomy_stage = (
        "Networked" if autonomy_level >= 3
        else "Living" if autonomy_level >= 1
        else "Static"
    )
    autonomy_desc = {
        "Static": "Manual sources · manual compile. Answers queries; nothing runs on its own.",
        "Living": "Auto-ingests from connected feeds and keeps compiled Wiki in sync with your sources.",
        "Networked": "Subscribes to peer KBs, absorbs their updates, and exposes its own compiled pages for them to subscribe back.",
    }[autonomy_stage]
    lines.append("## Autonomy stage")
    lines.append("")
    lines.append(f"**{autonomy_stage}** — {autonomy_desc}")
    lines.append("")

    # Footer — pointer to the describe endpoint for agents
    lines.append("---")
    lines.append("")
    lines.append(
        "_This manifest is the agent-facing identity card for this KB. "
        "Discovery agents read it via the `describe` tool. It auto-updates as the corpus grows._"
    )

    return "\n".join(lines)


def get_manifest_doc_id(corpus_id: str) -> str | None:
    """Return the id of this corpus's manifest doc, or None if absent."""
    row = get_conn().execute(
        "SELECT id FROM documents WHERE corpus_id=? AND doc_type=? LIMIT 1",
        (corpus_id, MANIFEST_DOC_TYPE),
    ).fetchone()
    return row["id"] if row else None


def ensure_manifest_doc(corpus_id: str) -> str:
    """Create the manifest doc for this corpus if missing. Returns doc id.

    Safe to call multiple times — idempotent. Called on corpus create and
    lazily whenever a corpus is loaded without one (backfill for existing
    corpora predating this feature).
    """
    existing = get_manifest_doc_id(corpus_id)
    if existing:
        return existing

    from noosphere.core.corpus import get_corpus

    corpus = get_corpus(corpus_id)
    if not corpus:
        raise ValueError(f"Corpus {corpus_id} not found")

    content = render_manifest_markdown(corpus)
    doc_id = uuid.uuid4().hex[:12]
    now = _now()

    # word_count on the rendered markdown so sidebar stats stay consistent.
    wc = len(content.split())

    # source_kind='system' — auto-generated metadata, NOT user content.
    # Excluded from the "originals" gate for pricing/publish, from
    # document_count stats, and from external-caller retrieval (the
    # /describe endpoint already exposes the same info to agents).
    get_conn().execute(
        """INSERT INTO documents
           (id, corpus_id, title, content, doc_type, date,
            word_count, content_hash, source_kind, author_entity_id,
            participant_entity_ids, tags, metadata_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id, corpus_id, "Manifest", content, MANIFEST_DOC_TYPE, "",
            wc, "", "system", None,
            "[]", "[]",
            json.dumps({"auto_generated": True, "pinned": True}),
            now,
        ),
    )
    get_conn().commit()
    return doc_id


def refresh_manifest_doc(corpus_id: str) -> None:
    """Rewrite the manifest doc's content from the corpus's current fields.

    No-op if no manifest doc exists (use ensure_manifest_doc first). This
    keeps the doc in sync with the canonical corpus row after edits.
    """
    from noosphere.core.corpus import get_corpus

    doc_id = get_manifest_doc_id(corpus_id)
    if not doc_id:
        return

    corpus = get_corpus(corpus_id)
    if not corpus:
        return

    content = render_manifest_markdown(corpus)
    wc = len(content.split())

    get_conn().execute(
        "UPDATE documents SET content=?, word_count=? WHERE id=?",
        (content, wc, doc_id),
    )
    get_conn().commit()
