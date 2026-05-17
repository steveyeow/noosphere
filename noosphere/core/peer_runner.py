"""Outbound peer subscription runner — L3 Networked autonomy.

Executes a single subscription cycle: pull from the peer, then **stage** the
results as pending review (source_kind='peer_subscription' carried in
metadata) — it never writes straight into the subscriber's corpus. The
owner approves or discards the staged cycle (review-before-apply); see
peer_subscriptions.stage_pending / approve_pending. "Human always wins"
across the trust boundary, since a subscription pulls from a corpus the
owner does not control.

Budget enforcement is recorded (`cents_spent`) but not gated here.
"""

import json
import logging
import time
import uuid

import httpx

from noosphere.core.corpus import get_corpus
from noosphere.core.db import get_conn
from noosphere.core.peer_subscriptions import (
    bump_failure,
    get_subscription,
    mark_run,
    reset_failures,
    stage_pending,
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

    # Review-before-apply: stage the cycle as pending — never write straight
    # into the subscriber corpus. The owner approves/discards it later.
    staged = 0
    run_id = uuid.uuid4().hex[:12]
    if outcome == "ok" and docs:
        staged = stage_pending(sub["subscriber_corpus_id"], sub, run_id, docs)
        if staged == 0:
            outcome = "no_new_content"

    latency_ms = int((time.monotonic() - started) * 1000)
    mark_run(
        sub_id,
        outcome=outcome if not outcome.startswith("error:") else "error",
        docs_ingested=staged,
        cents_spent=cents,
        latency_ms=latency_ms,
        error_detail=None if outcome in ("ok", "no_new_content") else outcome,
        run_id=run_id,
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
        "docs_ingested": 0,        # nothing ingested — staged for review
        "pending": staged,
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
