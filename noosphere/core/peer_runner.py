"""Outbound peer subscription runner — L3 Networked autonomy.

Executes a single subscription cycle: pull from the peer, ingest results
as documents with source_kind='peer_subscription', log the run.

Follows the pseudo-code in docs/l3-networked.md §4.2. Phase 1 implements
the happy path + basic error handling (HTTP status mapping, content hash
dedupe via ingest_text). Budget enforcement and notifications are deferred
to Phase 3 — this runner records `cents_spent` but does not gate on budget.
"""

import json
import logging
import time

import httpx

from noosphere.core.corpus import get_corpus
from noosphere.core.db import get_conn
from noosphere.core.ingest import ingest_text
from noosphere.core.peer_subscriptions import (
    bump_failure,
    get_subscription,
    mark_run,
    reset_failures,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20.0


def _peer_display_name(sub: dict) -> str:
    if sub.get("target_slug"):
        return str(sub["target_slug"])
    if sub.get("target_corpus_id"):
        local = get_corpus(sub["target_corpus_id"])
        if local:
            return str(local.get("name") or local.get("slug") or local["id"])
    if sub.get("target_endpoint"):
        return str(sub["target_endpoint"])
    return "peer"


def _build_headers(sub: dict) -> dict[str, str]:
    h = {"X-Noosphere-Caller-Corpus": sub["subscriber_corpus_id"]}
    if sub.get("bearer_token"):
        h["Authorization"] = f"Bearer {sub['bearer_token']}"
    return h


def _provenance(sub: dict) -> dict:
    return {
        "subscription_id": sub["id"],
        "peer_corpus_id": sub.get("target_corpus_id"),
        "peer_endpoint": sub.get("target_endpoint"),
        "peer_name": _peer_display_name(sub),
    }


def _ingest_peer_document(
    subscriber_id: str, sub: dict, *, title: str, content: str,
    doc_type: str, tags: list[str] | None = None,
    extra_meta: dict | None = None,
) -> dict | None:
    meta = _provenance(sub)
    if extra_meta:
        meta.update(extra_meta)
    # Content hash dedupe inside ingest_text isn't automatic; we pre-check here
    # so repeated pulls of the same doc don't litter the doc list.
    if _already_ingested(subscriber_id, content):
        return None
    return ingest_text(
        subscriber_id,
        title=title or "Untitled",
        content=content,
        doc_type=doc_type,
        source_kind="peer_subscription",
        tags=tags or [],
        metadata=meta,
    )


def _already_ingested(corpus_id: str, content: str) -> bool:
    import hashlib
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    row = get_conn().execute(
        "SELECT id FROM documents WHERE corpus_id=? AND content_hash=? LIMIT 1",
        (corpus_id, h),
    ).fetchone()
    return row is not None


def _run_ask_local(sub: dict, target_corpus_id: str) -> tuple[str, list[dict], int]:
    """Execute an ask against a locally-hosted peer — skip HTTP."""
    from noosphere.core.kb_agent import ask as kb_ask
    result = kb_ask(
        target_corpus_id, sub.get("query") or "",
        top_k=5, caller="external",
        agent_id=f"peer:{sub['subscriber_corpus_id']}",
    )
    if not result:
        return "no_new_content", [], 0
    answer = (result.get("answer") or "").strip()
    if not answer or result.get("out_of_scope"):
        return "no_new_content", [], 0
    doc = {
        "title": f"Peer answer: {(sub.get('query') or '').strip()[:80]}",
        "content": answer,
        "doc_type": "peer_answer",
        "tags": ["peer_subscription"],
        "extra_meta": {"question": sub.get("query"), "citations": result.get("citations", [])},
    }
    return "ok", [doc], 0


def _run_ask_remote(sub: dict) -> tuple[str, list[dict], int]:
    url = f"{str(sub['target_endpoint']).rstrip('/')}/ask"
    try:
        resp = httpx.post(url, json={"question": sub.get("query") or ""},
                          headers=_build_headers(sub), timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as e:
        return f"error:{e.__class__.__name__}", [], 0
    status = _status_outcome(resp)
    if status != "ok":
        return status, [], 0
    data = resp.json()
    answer = (data.get("answer") or "").strip()
    if not answer or data.get("out_of_scope"):
        return "no_new_content", [], 0
    return "ok", [{
        "title": f"Peer answer: {(sub.get('query') or '').strip()[:80]}",
        "content": answer,
        "doc_type": "peer_answer",
        "tags": ["peer_subscription"],
        "extra_meta": {"question": sub.get("query"), "citations": data.get("citations", [])},
    }], 0


def _run_describe_local(sub: dict, target_corpus_id: str) -> tuple[str, list[dict], int]:
    from noosphere.core.kb_agent import describe as kb_describe
    card = kb_describe(target_corpus_id)
    if not card:
        return "peer_down", [], 0
    return "ok", [_describe_doc(sub, card)], 0


def _run_describe_remote(sub: dict) -> tuple[str, list[dict], int]:
    url = f"{str(sub['target_endpoint']).rstrip('/')}/describe"
    try:
        resp = httpx.get(url, headers=_build_headers(sub), timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as e:
        return f"error:{e.__class__.__name__}", [], 0
    status = _status_outcome(resp)
    if status != "ok":
        return status, [], 0
    return "ok", [_describe_doc(sub, resp.json())], 0


def _describe_doc(sub: dict, card: dict) -> dict:
    name = card.get("name") or _peer_display_name(sub)
    body_lines = [f"# {name}"]
    if card.get("description"):
        body_lines.append(str(card["description"]))
    if card.get("tags"):
        body_lines.append("Tags: " + ", ".join(map(str, card["tags"])))
    if card.get("task_types"):
        body_lines.append("Task types: " + ", ".join(map(str, card["task_types"])))
    if card.get("source_composition"):
        body_lines.append("Source mix: " + json.dumps(card["source_composition"]))
    return {
        "title": f"Capability card: {name}",
        "content": "\n\n".join(body_lines),
        "doc_type": "capability_card",
        "tags": ["peer_subscription"],
        "extra_meta": {"describe_payload": card},
    }


def _run_new_documents_local(sub: dict, target_corpus_id: str) -> tuple[str, list[dict], int]:
    from noosphere.core.ingest import get_documents
    docs = get_documents(target_corpus_id)
    return _filter_new_documents(sub, docs)


def _run_new_documents_remote(sub: dict) -> tuple[str, list[dict], int]:
    url = f"{str(sub['target_endpoint']).rstrip('/')}/documents"
    try:
        resp = httpx.get(url, headers=_build_headers(sub), timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as e:
        return f"error:{e.__class__.__name__}", [], 0
    status = _status_outcome(resp)
    if status != "ok":
        return status, [], 0
    try:
        docs = resp.json()
        if not isinstance(docs, list):
            docs = docs.get("documents", []) if isinstance(docs, dict) else []
    except Exception:
        docs = []
    return _filter_new_documents(sub, docs)


def _filter_new_documents(sub: dict, docs: list[dict]) -> tuple[str, list[dict], int]:
    since = sub.get("last_run_at") or ""
    topic = (sub.get("topic_filter") or "").strip().lower()
    max_docs = int(sub.get("max_docs_per_cycle") or 5)

    out: list[dict] = []
    for d in docs:
        if len(out) >= max_docs:
            break
        # Skip docs that the peer itself marked as peer_subscription content —
        # prevents trivial A→B→A loops (loop-detection §9.5 is Phase 4).
        if (d.get("source_kind") or "") == "peer_subscription":
            continue
        created_at = d.get("created_at") or d.get("date") or ""
        if since and created_at and created_at < since:
            continue
        if topic:
            haystack = " ".join([
                str(d.get("title") or ""),
                " ".join(d.get("tags") or []) if isinstance(d.get("tags"), list) else str(d.get("tags") or ""),
            ]).lower()
            if topic not in haystack:
                continue
        content = d.get("content") or ""
        if not content.strip():
            continue
        out.append({
            "title": d.get("title") or "Untitled",
            "content": content,
            "doc_type": d.get("doc_type") or "doc",
            "tags": d.get("tags") if isinstance(d.get("tags"), list) else [],
            "extra_meta": {
                "peer_document_id": d.get("id"),
                "peer_document_date": d.get("date"),
            },
        })
    if not out:
        return "no_new_content", [], 0
    return "ok", out, 0


def _status_outcome(resp: httpx.Response) -> str:
    if resp.status_code == 200:
        return "ok"
    if resp.status_code in (401, 402, 403):
        return "auth_failed"
    if resp.status_code == 429:
        return "rate_limited"
    if 500 <= resp.status_code < 600:
        return "peer_down"
    return f"error:http_{resp.status_code}"


def run_subscription(sub_id: str) -> dict:
    """Execute a single subscription cycle. Always logs a run row.

    Returns {'sub_id', 'outcome', 'docs_ingested', 'cents_spent', 'latency_ms'}.
    Never raises — all errors are captured in the run log.
    """
    started = time.monotonic()
    sub = get_subscription(sub_id)
    if not sub:
        return {"sub_id": sub_id, "outcome": "error", "docs_ingested": 0}
    if sub["status"] != "active":
        return {"sub_id": sub_id, "outcome": "skipped_inactive", "docs_ingested": 0}

    mode = sub["mode"]
    local_target_id = sub.get("target_corpus_id")
    has_local = bool(local_target_id) and bool(get_corpus(local_target_id))
    has_endpoint = bool(sub.get("target_endpoint"))

    try:
        if mode == "ask":
            if has_local:
                outcome, docs, cents = _run_ask_local(sub, local_target_id)
            elif has_endpoint:
                outcome, docs, cents = _run_ask_remote(sub)
            else:
                outcome, docs, cents = "peer_down", [], 0
        elif mode == "describe":
            if has_local:
                outcome, docs, cents = _run_describe_local(sub, local_target_id)
            elif has_endpoint:
                outcome, docs, cents = _run_describe_remote(sub)
            else:
                outcome, docs, cents = "peer_down", [], 0
        elif mode == "new_documents":
            if has_local:
                outcome, docs, cents = _run_new_documents_local(sub, local_target_id)
            elif has_endpoint:
                outcome, docs, cents = _run_new_documents_remote(sub)
            else:
                outcome, docs, cents = "peer_down", [], 0
        else:
            outcome, docs, cents = "error", [], 0
    except Exception as e:
        logger.exception("peer_subscription %s crashed", sub_id)
        mark_run(
            sub_id, outcome="error",
            latency_ms=int((time.monotonic() - started) * 1000),
            error_detail=str(e),
        )
        bump_failure(sub_id, str(e))
        return {"sub_id": sub_id, "outcome": "error", "docs_ingested": 0}

    ingested = 0
    if outcome == "ok" and docs:
        for d in docs:
            saved = _ingest_peer_document(
                sub["subscriber_corpus_id"], sub,
                title=d["title"], content=d["content"],
                doc_type=d.get("doc_type", "doc"),
                tags=d.get("tags"),
                extra_meta=d.get("extra_meta"),
            )
            if saved:
                ingested += 1
        if ingested == 0:
            outcome = "no_new_content"

    latency_ms = int((time.monotonic() - started) * 1000)
    mark_run(
        sub_id,
        outcome=outcome if not outcome.startswith("error:") else "error",
        docs_ingested=ingested,
        cents_spent=cents,
        latency_ms=latency_ms,
        error_detail=None if outcome in ("ok", "no_new_content") else outcome,
    )
    if outcome in ("ok", "no_new_content"):
        reset_failures(sub_id)
    elif outcome in ("peer_down", "rate_limited") or outcome.startswith("error"):
        bump_failure(sub_id, outcome)
    elif outcome == "auth_failed":
        # One strike — owner needs to fix token/budget. Pause immediately.
        conn = get_conn()
        conn.execute(
            "UPDATE peer_subscriptions SET status='paused', last_error=? WHERE id=?",
            (outcome, sub_id),
        )
        conn.commit()

    return {
        "sub_id": sub_id,
        "outcome": outcome,
        "docs_ingested": ingested,
        "cents_spent": cents,
        "latency_ms": latency_ms,
    }


def run_due_subscriptions(limit: int = 20) -> list[dict]:
    """Scheduler tick — run up to N due subscriptions."""
    from noosphere.core.peer_subscriptions import due_subscriptions
    results = []
    for sub in due_subscriptions(limit=limit):
        results.append(run_subscription(sub["id"]))
    return results
