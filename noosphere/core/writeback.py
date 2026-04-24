"""Writeback — expose Noosphere-synthesized entity and concept pages as
markdown payloads for a CLI sync client to mirror into a user's vault.

Pattern mirrors Karpathy's `wiki/` layer: the LLM-maintained pages become
files in the user's filesystem, alongside the raw sources they imported.
For Noosphere-specific usage this keeps the vault as the ultimate system
of record — if the server disappears, the synthesis is still on disk.

Two page types are written back:

  - **Entities** → one file per entity with a compiled `description`.
    Skipped if `description` is empty. Frontmatter includes canonical_name,
    aliases, kind, and Noosphere ids so the client can round-trip.
  - **Concept docs** → every `doc_type='concept'` document. These are the
    fused wiki pages produced by the Compile flow. Frontmatter carries
    version, source_doc_ids, last_compiled_at.

The endpoint supports `since=ISO8601` for incremental polling; the CLI
persists the last-seen timestamp in `<vault>/__noosphere/.sync-state.json`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from noosphere.core.db import get_conn


def _slugify(text: str, *, max_len: int = 60) -> str:
    """Filesystem-safe slug derived from canonical name / title.

    Kept ASCII-lean so vaults sync across OS filesystems without surprises.
    Empty input falls back to 'untitled' so callers can use slug as the
    filename directly.
    """
    s = (text or "").strip().lower()
    s = re.sub(r"[^\w\s\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    s = s.strip("-")
    return (s or "untitled")[:max_len]


def _yaml_frontmatter(meta: dict[str, Any]) -> str:
    """Minimal YAML frontmatter writer. Scalars inlined; lists emitted as
    inline ``[a, b]``. Good enough for Noosphere writeback — the client
    isn't expected to do fancy YAML parsing either."""
    lines = ["---"]
    for k, v in meta.items():
        if v is None or v == "":
            continue
        if isinstance(v, list):
            items = ", ".join(json.dumps(x, ensure_ascii=False) for x in v)
            lines.append(f"{k}: [{items}]")
        elif isinstance(v, (int, float, bool)):
            lines.append(f"{k}: {v}")
        else:
            # Strings — escape newlines and wrap in double quotes.
            val = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
            lines.append(f'{k}: "{val}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def compute_writeback(corpus_id: str, *, since: str | None = None) -> dict[str, Any]:
    """Return writeback payload for a corpus.

    Shape::
        {
          "corpus_id": "...",
          "generated_at": "2026-04-24T...",
          "since": "<echoed filter>",
          "files": [
            {
              "path": "entities/alice.md",
              "content": "...markdown with frontmatter...",
              "updated_at": "2026-04-24T...",
              "kind": "entity"  # or "concept"
            },
            ...
          ]
        }

    `since` is an ISO8601 string; only items with updated_at/compiled_at
    strictly greater than `since` are included. When None, all eligible
    items are returned (initial writeback).
    """
    conn = get_conn()
    files: list[dict[str, Any]] = []

    # ── Entities with a compiled description ─────────────────────────────
    ent_sql = (
        "SELECT id, kind, canonical_name, aliases, description, updated_at "
        "FROM entities "
        "WHERE corpus_id=? AND description IS NOT NULL AND description != ''"
    )
    ent_args: list[Any] = [corpus_id]
    if since:
        ent_sql += " AND updated_at > ?"
        ent_args.append(since)
    for row in conn.execute(ent_sql, ent_args).fetchall():
        try:
            aliases = json.loads(row["aliases"] or "[]")
        except (json.JSONDecodeError, TypeError):
            aliases = []
        fm = {
            "source": "noosphere",
            "kind": row["kind"],
            "canonical_name": row["canonical_name"],
            "aliases": aliases,
            "noosphere_entity_id": row["id"],
            "noosphere_corpus_id": corpus_id,
            "updated_at": row["updated_at"],
        }
        content = _yaml_frontmatter(fm) + (row["description"] or "").strip() + "\n"
        files.append({
            "path": f"entities/{_slugify(row['canonical_name'])}.md",
            "content": content,
            "updated_at": row["updated_at"],
            "kind": "entity",
        })

    # ── Concept documents (latest version of each) ───────────────────────
    # Join to concept_versions so we get the authoritative compile timestamp
    # (documents table has no updated_at).
    cv_sql = (
        "SELECT d.id, d.title, d.content, d.metadata_json, "
        "       (SELECT MAX(compiled_at) FROM concept_versions cv WHERE cv.document_id=d.id) AS last_compiled "
        "FROM documents d "
        "WHERE d.corpus_id=? AND d.doc_type='concept'"
    )
    cv_args: list[Any] = [corpus_id]
    rows = conn.execute(cv_sql, cv_args).fetchall()
    for row in rows:
        last_compiled = row["last_compiled"] or ""
        if since and last_compiled and last_compiled <= since:
            continue
        # Fallback for concept docs with no versions yet — use created_at
        # if available via the documents query (we don't select it, so
        # just mark undated). In practice every compile writes a version.
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        fm = {
            "source": "noosphere",
            "doc_type": "concept",
            "title": row["title"],
            "noosphere_document_id": row["id"],
            "noosphere_corpus_id": corpus_id,
            "last_compiled_at": last_compiled or "",
            "version": meta.get("version", 1),
            "source_document_ids": meta.get("source_document_ids", []),
        }
        content = _yaml_frontmatter(fm) + (row["content"] or "").strip() + "\n"
        files.append({
            "path": f"concepts/{_slugify(row['title'])}.md",
            "content": content,
            "updated_at": last_compiled or datetime.now(timezone.utc).isoformat(),
            "kind": "concept",
        })

    return {
        "corpus_id": corpus_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "since": since or "",
        "files": files,
    }
