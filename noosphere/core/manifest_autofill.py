"""LLM-driven manifest auto-fill.

When a corpus is first ingested, the agent-media capability card fields
(`task_types`, `samples`, refreshed `description`) should be populated from
the actual content — not left empty for the owner to fill manually.

This module reads corpus documents + tags, asks the LLM to propose the
structured fields, and returns the proposal as a dict. Callers decide whether
to apply (silently or behind owner approval).

Pro-tier feature in cloud mode; free in self-hosted when an LLM is configured.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from noosphere.core.corpus import get_corpus
from noosphere.core.db import get_conn
from noosphere.core.llm import LLMError, call_llm

log = logging.getLogger(__name__)

# How many documents to sample as LLM context. Too few → biased; too many →
# token cost. 12 is a decent default for most corpora.
SAMPLE_DOCS = 12
# Max chars per document in the prompt. Truncation is fine for inference —
# we only need the shape, not the full content.
MAX_CHARS_PER_DOC = 400

SYSTEM_PROMPT = """You analyze a knowledge base's content and produce a structured capability card that helps AI agents discover it.

Respond with ONLY a JSON object matching this exact schema:
{
  "task_types": ["synthesis" | "retrieval" | "advice" | "how-to" | "factual-lookup" | "comparison", ...],
  "samples": [
    {"question": "a concrete question this KB answers well", "answer_preview": "one sentence of what the answer would contain"},
    ...
  ],
  "description_suggestion": "a crisp 1-2 sentence description that captures the KB's actual scope"
}

Rules:
- task_types: pick 2-4 from the enum above that best describe how agents query this KB.
- samples: 2-3 realistic example questions grounded in the content shown. Each answer_preview must be at most one sentence.
- description_suggestion: match the tone of the existing description if one is given; refine for clarity.
- Output valid JSON only — no prose, no markdown fences, no commentary.
"""


def _load_sampled_docs(corpus_id: str) -> list[dict]:
    rows = get_conn().execute(
        """SELECT title, content, doc_type, tags FROM documents
           WHERE corpus_id=?
           ORDER BY created_at DESC
           LIMIT ?""",
        (corpus_id, SAMPLE_DOCS),
    ).fetchall()
    return [dict(r) for r in rows]


def _build_user_prompt(corpus: dict, docs: list[dict]) -> str:
    lines = [
        f"Knowledge base name: {corpus.get('name', '')}",
        f"Current description: {corpus.get('description', '') or '(none)'}",
        f"Current tags: {corpus.get('tags') or []}",
        "",
        f"Sample documents ({len(docs)} of {corpus.get('document_count', 0)} total):",
    ]
    for d in docs:
        content = (d.get("content") or "").strip()
        if len(content) > MAX_CHARS_PER_DOC:
            content = content[: MAX_CHARS_PER_DOC - 3] + "..."
        lines.append(f"\n--- Document: {d.get('title', 'Untitled')} ({d.get('doc_type') or 'doc'}) ---")
        lines.append(content)
    lines.append("\nReturn the JSON capability card now.")
    return "\n".join(lines)


def _parse_proposal(raw: str) -> dict:
    """Extract JSON from an LLM response. LLMs sometimes wrap in fences or add
    prose despite instructions; try a few recovery strategies.
    """
    text = raw.strip()
    # Strip common markdown fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    # If there's trailing prose, trim to the last closing brace
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        text = text[start:end]
    return json.loads(text)


def _normalize_proposal(proposal: Any, corpus: dict) -> dict:
    """Clamp LLM output to the expected shape + bounded sizes."""
    if not isinstance(proposal, dict):
        raise ValueError("LLM response was not a JSON object")

    valid_task_types = {
        "synthesis", "retrieval", "advice", "how-to", "factual-lookup", "comparison",
    }
    task_types = proposal.get("task_types") or []
    if isinstance(task_types, str):
        task_types = [task_types]
    task_types = [
        t for t in task_types if isinstance(t, str) and t in valid_task_types
    ][:4]

    samples = proposal.get("samples") or []
    clean_samples = []
    for s in samples[:3]:
        if not isinstance(s, dict):
            continue
        q = (s.get("question") or "").strip()[:300]
        a = (s.get("answer_preview") or "").strip()[:300]
        if q and a:
            clean_samples.append({"question": q, "answer_preview": a})

    description = (proposal.get("description_suggestion") or "").strip()[:500]

    return {
        "task_types": task_types,
        "samples": clean_samples,
        "description_suggestion": description,
    }


def suggest_manifest(corpus_id: str) -> dict | None:
    """Ask the LLM to propose manifest fields for a corpus.

    Returns a dict with `task_types`, `samples`, `description_suggestion`.
    Returns None if the corpus has no content yet (nothing to infer from).
    Raises LLMError on provider failure.
    """
    corpus = get_corpus(corpus_id)
    if not corpus:
        return None
    docs = _load_sampled_docs(corpus_id)
    if not docs:
        return None

    prompt = _build_user_prompt(corpus, docs)
    raw = call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    try:
        proposal = _parse_proposal(raw)
    except (ValueError, json.JSONDecodeError) as e:
        log.warning(f"manifest_autofill: could not parse LLM response ({e}): {raw[:200]!r}")
        return None
    return _normalize_proposal(proposal, corpus)


def apply_proposal(corpus_id: str, proposal: dict, *, refresh_description: bool = False) -> dict:
    """Persist a proposal to the corpus manifest.

    By default only `task_types` and `samples` are written; the description is
    treated as a suggestion the owner may or may not want applied. Pass
    `refresh_description=True` to overwrite description too.
    """
    from noosphere.core.corpus import update_corpus

    updates: dict[str, Any] = {}
    if isinstance(proposal.get("task_types"), list):
        updates["task_types"] = proposal["task_types"]
    if isinstance(proposal.get("samples"), list):
        updates["samples"] = proposal["samples"]
    if refresh_description and proposal.get("description_suggestion"):
        updates["description"] = proposal["description_suggestion"]
    if not updates:
        return get_corpus(corpus_id)
    return update_corpus(corpus_id, **updates)


def autofill_if_empty(corpus_id: str) -> dict | None:
    """Post-ingest convenience hook: if the manifest's agent-media fields are
    empty and the corpus has content, generate and apply a proposal.

    No-op if `task_types` is already populated (owner may have customized).
    Returns the proposal applied, or None if skipped / failed.
    """
    corpus = get_corpus(corpus_id)
    if not corpus:
        return None
    if corpus.get("task_types"):
        return None  # owner (or previous run) already filled
    try:
        proposal = suggest_manifest(corpus_id)
    except LLMError as e:
        log.info(f"manifest_autofill skipped ({e})")
        return None
    if not proposal:
        return None
    apply_proposal(corpus_id, proposal, refresh_description=False)
    return proposal
