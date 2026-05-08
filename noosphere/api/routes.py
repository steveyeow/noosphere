"""REST API routes for corpus operations and network discovery."""

import json as _json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, UploadFile, File, Form
from pydantic import BaseModel

from noosphere import __version__
from noosphere.core.corpus import LOCAL_OWNER_ID, DuplicateCorpusName, list_corpora, list_user_corpora, get_corpus, get_corpus_by_slug, create_corpus, update_corpus, delete_corpus, source_composition
from noosphere.core.ingest import get_documents, get_document, ingest_text, ingest_url, delete_document, update_document
from noosphere.core.retrieval import search_corpus
from noosphere.core.kb_agent import ask as kb_ask, describe as kb_describe, preview_ask as kb_preview_ask, route as kb_route
from noosphere.core.access import check_access, AccessDenied, PaymentRequired, verify_facilitator_proof
from noosphere.core.access_log import log_access
from noosphere.core.db import get_conn, is_pg
from noosphere.core.llm import LLMError
from noosphere.core import orgs as orgs_mod

# Cloud quota helpers — no-ops when ENABLE_CLOUD is off or user is not authenticated
def _check_quota(request: Request, action: str):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_quota
        check_quota(request, action)
    except ImportError:
        pass

def _check_corpus_limit(request: Request):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_corpus_limit
        check_corpus_limit(request)
    except ImportError:
        pass

def _check_document_limit(request: Request, corpus_id: str):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import check_document_limit
        check_document_limit(request, corpus_id)
    except ImportError:
        pass

def _track_usage(request: Request, action: str, tokens_used: int = 0):
    if not _is_cloud():
        return
    try:
        from noosphere.cloud.quota import track_usage
        track_usage(request, action, tokens_used)
    except ImportError:
        pass

router = APIRouter()

_CLOUD_MODE = os.getenv("ENABLE_CLOUD", "").lower() in ("1", "true", "yes") if "os" in dir() else False

def _is_cloud() -> bool:
    from noosphere.core.config import ENABLE_CLOUD
    return ENABLE_CLOUD


def _get_user_id(request: Request) -> str | None:
    """Resolve the requesting user_id.

    Cloud mode: from JWT-validated request.state (set by auth middleware).
    Self-hosted: ``X-Noosphere-User-Id`` header (browser-issued, persisted in
    localStorage) wins. If absent and the caller is the localhost operator,
    returns the sentinel ``LOCAL_OWNER_ID``. Otherwise None — anonymous reader.
    """
    state_uid = getattr(request.state, "user_id", None)
    if state_uid:
        return state_uid
    if _is_cloud():
        return None
    header_uid = request.headers.get("x-noosphere-user-id", "").strip()
    if header_uid:
        return header_uid
    if _is_owner_request(request):
        return LOCAL_OWNER_ID
    return None


def _client_ip(request: Request) -> str | None:
    client = request.client
    return getattr(client, "host", None) if client else None


def _active_workspace(request: Request) -> tuple[str, str | None]:
    """Parse the active workspace from the X-Noosphere-Workspace header.

    Returns ``("personal", None)`` or ``("org", <org_id>)``. Defaults to
    personal when the header is missing or malformed.
    """
    raw = request.headers.get("x-noosphere-workspace", "").strip().lower()
    if raw.startswith("org:"):
        org_id = raw[4:].strip()
        if org_id:
            return ("org", org_id)
    return ("personal", None)


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _is_owner_request(request: Request) -> bool:
    """Check if the request comes from the owner (local web UI or localhost).

    In self-hosted mode, the person running the server is the owner.
    Access control only restricts external agent/API consumers.
    Owner is identified by: connecting from localhost, or having a
    same-origin Referer, or not having an X-Agent-ID header while
    connecting from the local network.
    """
    if request.headers.get("x-agent-id"):
        return False

    client = request.client
    if client:
        host = client.host or ""
        if host in ("127.0.0.1", "::1", "localhost", "0.0.0.0", "testclient"):
            return True

    referer = request.headers.get("referer", "")
    if referer:
        base = str(request.base_url).rstrip("/")
        if referer.startswith(base):
            return True
        if "://localhost:" in referer or "://127.0.0.1:" in referer:
            return True

    origin = request.headers.get("origin", "")
    if origin and ("://localhost:" in origin or "://127.0.0.1:" in origin):
        return True

    return False


def _check_corpus_access(corpus: dict, request: Request) -> str | None:
    """Enforce access control. Returns token_id if token auth was used.

    Personal corpus: owner request (localhost / matching user_id) bypasses;
    other readers fall through to public/token/paid gating.
    Team corpus: any org member with role >= viewer bypasses; non-members
    fall through to gating just like for personal corpora.

    Paid-corpus agent path: if the bearer doesn't validate (no Stripe
    payment) and an `X-PAYMENT` header is present, the configured
    facilitator (Coinbase x402, Mock, etc.) is given a chance to verify
    the proof. Successful verification grants this single request and
    records an `agent_settlements` row for audit. Otherwise the request
    is denied with a `PaymentRequired` exception, which the global
    handler turns into a proper x402 JSON challenge body.
    """
    user_id = _get_user_id(request)
    if corpus.get("org_id"):
        if user_id and orgs_mod.can_read_corpus(corpus, user_id):
            return None
    else:
        if _is_owner_request(request):
            return None
        if _is_cloud() and user_id and corpus.get("owner_id") == user_id:
            return None
    try:
        return check_access(corpus, _extract_bearer(request))
    except AccessDenied as e:
        if e.status_code == 402:
            payment_proof = (request.headers.get("x-payment") or "").strip()
            resource = str(request.url.path)
            if payment_proof:
                agent_id = request.headers.get("x-agent-id", "")
                result, settlement_id = verify_facilitator_proof(
                    corpus, payment_proof, resource=resource, agent_id=agent_id,
                )
                if result.valid:
                    return settlement_id
            raise PaymentRequired(corpus, resource=resource)
        raise HTTPException(status_code=e.status_code, detail=e.message)


def _require_owner(request: Request, corpus: dict | None = None):
    """Require write access on a corpus or the instance.

    Personal corpus:
      - Cloud: caller's user_id must match owner_id.
      - Self-hosted: localhost OR matching X-Noosphere-User-Id.
    Team corpus (org_id set):
      - Caller must be an org member with role >= editor.
    No corpus passed: must be a localhost operator (cloud: any authed user).
    """
    user_id = _get_user_id(request)

    if corpus and corpus.get("org_id"):
        if not user_id or not orgs_mod.can_write_corpus(corpus, user_id):
            raise HTTPException(status_code=403, detail="Write access restricted to org editors")
        return

    if _is_cloud():
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        if corpus and corpus.get("owner_id") and corpus["owner_id"] != user_id:
            raise HTTPException(status_code=403, detail="You do not own this corpus")
        return

    if corpus and corpus.get("owner_id") and user_id and corpus["owner_id"] == user_id:
        return
    if not _is_owner_request(request):
        raise HTTPException(status_code=403, detail="Write access restricted to corpus owner")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    include_context: bool = True
    detail: str = "medium"  # low | medium | high


class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class PreviewAskRequest(BaseModel):
    question: str


class RouteRequest(BaseModel):
    question: str
    limit: int = 5


class CitationRequest(BaseModel):
    cited_corpus_id: str
    cited_corpus_endpoint: str = ""
    context: str = ""


class ManifestApplyRequest(BaseModel):
    task_types: list[str] | None = None
    samples: list[dict] | None = None
    description_suggestion: str | None = None
    refresh_description: bool = False


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    top_k: int = 5
    session_id: Optional[str] = None


class TerminalRequest(BaseModel):
    input: str
    context: dict = {}
    # Composer mode the home terminal is in when this request fires.
    # 'enrich' = chat with existing corpora (default); 'create' = LLM
    # extracts a topic from the input and spins up a new KB. 'compile'
    # is handled client-side (it navigates straight to the canvas) and
    # never reaches /terminal, but we accept it here defensively so a
    # future move of that logic to the backend doesn't break the schema.
    mode: str = "enrich"
    # Active corpus when sent from a corpus-scoped composer (corpus detail
    # page dock, or the home composer with a chip selection). When set, the
    # URL/note path skips the "Which corpus?" picker and ingests directly,
    # and the route persists the round-trip as a chat session.
    corpus_id: Optional[str] = None


class CreateCorpusRequest(BaseModel):
    name: str
    description: str = ""
    author_name: str = ""
    tags: list[str] = []
    # access_level is workspace-aware:
    #   personal → defaults to "public" (creator-friendly publish flow)
    #   org      → defaults to "private" (team data rarely goes public)
    # Pass an explicit value to override.
    access_level: Optional[str] = None
    language: str = "en"


class UpdateCorpusRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    access_level: Optional[str] = None
    tags: Optional[list[str]] = None
    owned_handles: Optional[list[str]] = None
    # Settable at create — historically locked once the corpus existed, so a
    # typo at create time stuck. All four are user-visible (language gates
    # search behavior; license + author surface in the public manifest).
    language: Optional[str] = None
    license_: Optional[str] = None
    author_name: Optional[str] = None
    author_url: Optional[str] = None


class UpdateDocumentRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    # Source attribution — kept editable post-import so users can correct a
    # doc that was misclassified at ingest time (e.g. a JS-blocked URL that
    # came in as external_public but the user later pastes their own text).
    # Validated against the same allow-list used at ingest time.
    source_kind: Optional[str] = None
    # date and metadata are extracted at ingest from HTML <meta> tags / file
    # frontmatter and are frequently wrong (LLM-generated dummies, missing
    # or misformatted). Allow post-hoc edits so users don't have to delete
    # and re-ingest just to fix an author or publish date.
    date: Optional[str] = None
    metadata: Optional[dict] = None


class IngestURLRequest(BaseModel):
    url: str
    doc_type: str = "blog"
    source_kind: Optional[str] = None


class IndexRequest(BaseModel):
    force: bool = False
    chunk_strategy: Optional[str] = None


class CaptureRequest(BaseModel):
    """Save chat output or notes back into the corpus (chat → knowledge base)."""

    content: str
    title: str = ""
    question: str = ""
    session_id: Optional[str] = None


class IngestFeedRequest(BaseModel):
    feed_url: str
    max_items: int = 25


class IngestUrlsRequest(BaseModel):
    urls: list[str]
    doc_type: str = "blog"
    source_kind: Optional[str] = None


class CompileRequest(BaseModel):
    topic: str
    top_k: int = 10


class RecompileRequest(BaseModel):
    """Force-recompile a living concept's compiled truth from its timeline sources."""
    force: bool = False


class RecompileDirtyRequest(BaseModel):
    """Batch recompile every concept in a corpus that is dirty (or all, with force)."""
    force: bool = False


class RefineRequest(BaseModel):
    """Natural-language edit instruction for a compiled concept or entity."""
    instruction: str


class MaintainRequest(BaseModel):
    force: bool = False


class CreateTokenRequest(BaseModel):
    label: str = ""
    permissions: str = "read"
    expires_at: str | None = None


class CreatePeerSubscriptionRequest(BaseModel):
    """Owner-approved subscription intent — see docs/l3-networked.md §3."""
    mode: str  # 'ask' | 'describe' | 'new_documents'
    target_corpus_id: Optional[str] = None
    target_endpoint: Optional[str] = None
    target_slug: Optional[str] = None
    query: Optional[str] = None
    topic_filter: Optional[str] = None
    cadence_minutes: int = 1440
    max_docs_per_cycle: int = 5
    bearer_token: Optional[str] = None
    auth_mode: str = "public"  # 'public' | 'token' | 'paid'
    budget_cents_per_month: Optional[int] = None


class UpdatePeerSubscriptionRequest(BaseModel):
    status: Optional[str] = None  # 'active' | 'paused'
    cadence_minutes: Optional[int] = None
    query: Optional[str] = None
    topic_filter: Optional[str] = None
    max_docs_per_cycle: Optional[int] = None
    budget_cents_per_month: Optional[int] = None


@router.post("/terminal")
async def api_terminal(req: TerminalRequest, request: Request):
    """Interactive terminal command handler."""
    # Workspace-aware Create mode: in an org workspace the new corpus must
    # land in the team scope, otherwise it ends up as a personal corpus the
    # team can't see. Authorize accordingly — org workspace requires editor+
    # role; personal falls back to the existing _require_owner check.
    kind, active_org = _active_workspace(request)
    if kind == "org" and active_org:
        _require_org_role(request, active_org, orgs_mod.ROLE_EDITOR)
    else:
        _require_owner(request)

    from noosphere.core.terminal import handle_terminal_input
    actor_uid = _get_user_id(request)
    # Cloud-only plumbing for Create mode: attribute new corpora to the
    # current user (otherwise list_user_corpora won't surface them) and
    # gate creation on the per-tier quota (otherwise this path silently
    # bypasses the limit that POST /corpora enforces).
    owner_id = actor_uid if _is_cloud() else ""
    org_id = active_org if kind == "org" else ""
    quota_check = (lambda: _check_corpus_limit(request)) if req.mode == "create" else None
    result = handle_terminal_input(
        req.input, req.context,
        mode=req.mode,
        owner_id=owner_id,
        org_id=org_id,
        contributor_user_id=actor_uid,
        quota_check=quota_check,
        corpus_id=req.corpus_id,
    )

    # Persist the round-trip as a chat session when scoped to a known corpus,
    # so the user finds it in the Chats sidebar afterward. Only persist when
    # the corpus actually resolved (skip mid-flow picker prompts and unknown
    # ids) and never persist Create-mode (it's about to land on a different
    # corpus the user has not opened yet).
    if req.corpus_id and req.mode != "create":
        ctx = result.get("context") or {}
        if ctx.get("state") != "pick_corpus":
            persisted = _persist_terminal_chat(
                corpus_id=req.corpus_id,
                user_input=req.input,
                lines=result.get("lines") or [],
                session_id=(req.context or {}).get("session_id"),
            )
            if persisted:
                ctx["session_id"] = persisted
                result["context"] = ctx
                result["session_id"] = persisted

    return result


def _persist_terminal_chat(
    *,
    corpus_id: str,
    user_input: str,
    lines: list,
    session_id: str | None,
) -> str | None:
    """Mirror the corpus chat path: append user + assistant rows so /terminal
    interactions inside a corpus surface in the Chats sidebar like any other
    chat. Returns the session id (new or extended), or None if the corpus
    can't be resolved.
    """
    import uuid
    from datetime import datetime, timezone

    corpus = get_corpus(corpus_id)
    if not corpus:
        return None

    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    if session_id:
        # Verify the session still exists — the row could have been deleted
        # (cascade from corpus delete, manual /chat-sessions/{id} DELETE, or
        # workspace switch). Without this check, we silently INSERT messages
        # against a dead session_id and the user's "continued" conversation
        # would never appear in the sidebar.
        existing = conn.execute(
            "SELECT id FROM chat_sessions WHERE id=? AND corpus_id=?",
            (session_id, corpus["id"]),
        ).fetchone()
        if not existing:
            session_id = None  # fall through to create-fresh path

    if not session_id:
        session_id = str(uuid.uuid4())
        title = (user_input or "").strip()[:80] or "Conversation"
        conn.execute(
            "INSERT INTO chat_sessions (id, corpus_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, corpus["id"], title, now, now),
        )
    else:
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))

    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, "user", user_input, now),
    )

    # Flatten the assistant response — terminal returns a list of typed lines
    # (resp/option/card). Concatenate the human-readable text fields so the
    # sidebar preview and the future re-open of this session show what Noos
    # actually said.
    assistant_text = "\n".join(
        (ln.get("text") or "").strip()
        for ln in lines
        if isinstance(ln, dict) and ln.get("type") in ("resp", "option") and ln.get("text")
    ).strip()
    if not assistant_text:
        # Cards are the only non-text line type carrying meaning — fall back
        # to a one-liner so the row isn't empty.
        assistant_text = "(action completed)"

    # Also store the structured lines so resuming the session can replay
    # the exact same sequence of bubbles + cards the user saw in-flight.
    # Drop empty/non-dict entries defensively; everything else passes
    # through verbatim because the frontend renderer (addLine) already
    # tolerates unknown fields.
    structured = [ln for ln in lines if isinstance(ln, dict) and ln.get("type")]
    lines_json = _json.dumps(structured) if structured else None

    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, lines_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, "assistant", assistant_text, lines_json, now),
    )
    conn.commit()
    return session_id


def _resolve_corpus(corpus_id: str) -> dict:
    corpus = get_corpus(corpus_id) or get_corpus_by_slug(corpus_id)
    if not corpus:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return corpus


@router.get("/health")
async def api_health(request: Request):
    corpora = list_corpora(include_private=True)
    conn = get_conn()
    try:
        remote_nodes = conn.execute("SELECT COUNT(*) as n FROM registered_nodes").fetchone()["n"]
        remote_corpora = conn.execute("SELECT COUNT(*) as n FROM registered_corpora").fetchone()["n"]
    except Exception:
        remote_nodes, remote_corpora = 0, 0
    # Registry status — self-hosted nodes register to the shared Noosphere
    # network by default (NOOSPHERE_REGISTRY defaults to the cloud registry
    # URL). Opt-out is via NOOSPHERE_REGISTRY=none. The frontend Discovery
    # row uses these two flags to render the correct state.
    #
    # registry_url      — the configured registry URL ("" = explicit opt-out)
    # registry_configured — true unless opted out
    # registry_connected — true if we've successfully registered + the registry
    #                      is reachable (checked via lightweight HEAD request
    #                      with a short timeout so /health stays fast)
    from noosphere.core.config import NOOSPHERE_REGISTRY, NOOSPHERE_IS_REGISTRY
    registry_url = NOOSPHERE_REGISTRY
    registry_configured = bool(registry_url)
    registry_connected = False
    if registry_configured:
        try:
            import httpx
            # Timeout was 2s originally — too tight for cross-region SSL
            # handshake (Railway hosts in SE-Asia; EU/US clients routinely
            # exceed 2s on TLS 1.3). 10s is comfortable for cold SSL pool
            # starts — empirically direct httpx.head takes ~5s on first
            # call, <1s after cert chain is cached. A worse false-negative
            # than a slow /health was getting "Registering… (retrying)"
            # shown forever.
            resp = httpx.head(registry_url.rstrip("/"), timeout=10, follow_redirects=True)
            # Registry itself answering is enough — don't gate on a 200 since
            # the root path may redirect or respond 405 (HEAD not allowed)
            # while /api/v1/register still works.
            registry_connected = resp.status_code < 500
        except Exception:
            registry_connected = False
    # Actual registration success — more reliable than the HEAD probe,
    # which can succeed while auth or other middleware blocks the real
    # POST. Set in register_with_registry() on success.
    from noosphere.core.registry import last_registration_ok
    # Profile-embedding pipeline diagnostics — surfaced here so an operator
    # can tell at a glance whether the discovery graph's semantic edges
    # are working. Three counts answer different questions:
    #   embedded — corpora that have a vector (graph can render their edges)
    #   dirty    — vectors exist but content drifted; pending lazy refresh
    #   missing  — corpora that have never been embedded; lazy backfill
    #              should pick them up on next /corpora/network call
    # column_present catches the boot-time failure mode where the
    # migration didn't apply (rare, but seeing dirty=missing=embedded=0
    # on a populated node would otherwise look indistinguishable from
    # "embedder is down").
    embedding_stats = {
        "embedded": 0, "dirty": 0, "missing": 0, "column_present": False,
    }
    try:
        _conn = get_conn()
        _row = _conn.execute(
            "SELECT "
            " SUM(CASE WHEN corpus_vector IS NOT NULL THEN 1 ELSE 0 END) AS embedded, "
            " SUM(CASE WHEN corpus_vector_dirty_since IS NOT NULL THEN 1 ELSE 0 END) AS dirty, "
            " SUM(CASE WHEN corpus_vector IS NULL THEN 1 ELSE 0 END) AS missing "
            "FROM corpora"
        ).fetchone()
        if _row is not None:
            embedding_stats["embedded"] = int(_row["embedded"] or 0)
            embedding_stats["dirty"] = int(_row["dirty"] or 0)
            embedding_stats["missing"] = int(_row["missing"] or 0)
            embedding_stats["column_present"] = True
    except Exception:
        # Column missing → migration didn't run. Leaves column_present=False
        # so the operator can tell the column itself is the problem.
        pass

    # Build identity — answers "is the running container actually the
    # commit I just pushed?" without having to grep Railway logs.
    # RAILWAY_GIT_COMMIT_SHA is set automatically by Railway at deploy
    # time; falls back to "" on self-hosted / local. Also publishes a
    # short list of route fingerprints (specifically the ones added in
    # recent commits) so an operator can confirm a particular endpoint
    # really shipped, distinct from the silent "old image still serving"
    # failure mode where /health returns fine but the new endpoint 404s.
    import os as _os
    git_sha = (_os.getenv("RAILWAY_GIT_COMMIT_SHA")
               or _os.getenv("GIT_COMMIT_SHA") or "")[:12]
    has_admin_recompute = any(
        getattr(r, "path", "") == "/api/v1/admin/recompute-embeddings"
        for r in request.app.routes
    )
    return {
        "status": "ok",
        "version": __version__,
        "git_sha": git_sha,
        "has_admin_recompute": has_admin_recompute,
        "corpus_count": len(corpora),
        "network_nodes": remote_nodes,
        "network_corpora": remote_corpora,
        "registry_url": registry_url,
        "registry_configured": registry_configured,
        "registry_connected": registry_connected,
        "registry_registration_ok": last_registration_ok(),
        # is_registry — this node IS the shared registry (e.g. noosphere.wiki).
        # Distinct from registry_configured: a registry node's corpora are
        # already on its own DB, so it's discoverable WITHOUT having to
        # outbound-register anywhere. UI uses this to render the right
        # status copy.
        "is_registry": NOOSPHERE_IS_REGISTRY,
        "embedding_stats": embedding_stats,
    }


# ── Profile ──

@router.get("/me")
async def api_me(request: Request):
    user_id = _get_user_id(request)
    workspace = _active_workspace(request)
    orgs_for_user = orgs_mod.list_orgs_for_user(user_id) if user_id else []
    # Annotate each org with its member count — feeds the workspace card
    # in the profile popover ("Team · 3 members"). Single small SELECT
    # per org; not in a hot path.
    if orgs_for_user:
        conn = get_conn()
        for o in orgs_for_user:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM organization_members WHERE org_id=?",
                (o["id"],),
            ).fetchone()
            o["member_count"] = row["n"] if row else 0
    workspace_dict = {"kind": workspace[0], "org_id": workspace[1]}
    if _is_cloud():
        email = getattr(request.state, "email", "")
        tier = getattr(request.state, "tier", "free")
        name = email.split("@")[0].replace(".", " ").title() if email else "User"
        return {
            "name": name, "user_id": user_id, "email": email, "tier": tier,
            "cloud": True,
            "active_workspace": workspace_dict, "orgs": orgs_for_user,
        }
    from noosphere.core.config import OWNER_NAME
    return {
        "name": OWNER_NAME, "user_id": user_id,
        "is_local_operator": _is_owner_request(request),
        "active_workspace": workspace_dict, "orgs": orgs_for_user,
    }


# ── Corpus CRUD ──

def _annotate_compile_state(corpora: list[dict]) -> list[dict]:
    """Attach concept_count + entity_count per corpus for list-view cards.

    Concept docs (doc_type='concept') are the synthesis output of /compile;
    entities are the enrichment output. Together they signal compile state
    without a schema change. Runs two batched aggregate queries, not N+1.
    """
    if not corpora:
        return corpora
    conn = get_conn()
    concept_rows = conn.execute(
        "SELECT corpus_id, COUNT(*) AS n FROM documents WHERE doc_type='concept' GROUP BY corpus_id"
    ).fetchall()
    entity_rows = conn.execute(
        "SELECT corpus_id, COUNT(*) AS n FROM entities GROUP BY corpus_id"
    ).fetchall()
    concepts = {r["corpus_id"]: r["n"] for r in concept_rows}
    entities = {r["corpus_id"]: r["n"] for r in entity_rows}
    for c in corpora:
        c["concept_count"] = concepts.get(c["id"], 0)
        c["entity_count"] = entities.get(c["id"], 0)
    return corpora


@router.get("/corpora")
async def api_list_corpora(request: Request):
    """List corpora scoped to the active workspace (header ``X-Noosphere-Workspace``).

    Org workspace → org-scoped corpora visible to the calling member.
    Personal workspace → corpora the caller owns (cloud / matching user_id) or
    public corpora (anonymous reader / self-hosted operator).
    """
    kind, org_id = _active_workspace(request)
    if kind == "org" and org_id:
        _require_org_member(request, org_id)
        rows = get_conn().execute(
            "SELECT * FROM corpora WHERE org_id=? ORDER BY updated_at DESC", (org_id,)
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for k in ("tags", "owned_handles", "task_types", "samples"):
                if isinstance(d.get(k), str):
                    try:
                        d[k] = _json.loads(d[k])
                    except Exception:
                        pass
            # Strip backend-only graph-embedding fields — they're raw
            # bytes that break FastAPI's JSON encoder, and the frontend
            # has no use for them. Mirrors corpus._row_to_dict.
            d.pop("corpus_vector", None)
            d.pop("corpus_vector_norm", None)
            out.append(d)
        return _annotate_compile_state(out)
    if _is_cloud():
        user_id = _get_user_id(request)
        if user_id:
            return _annotate_compile_state(list_user_corpora(user_id))
        all_c = list_corpora()
        return _annotate_compile_state([c for c in all_c if c.get("owner_id") or c.get("org_id")])
    listed = list_corpora(include_private=_is_owner_request(request))
    # Personal workspace must never leak org-scoped corpora — those only
    # surface when the caller switches to that org's workspace explicitly.
    listed = [c for c in listed if not c.get("org_id")]
    return _annotate_compile_state(listed)


@router.post("/corpora")
async def api_create_corpus(req: CreateCorpusRequest, request: Request, background_tasks: BackgroundTasks):
    kind, org_id = _active_workspace(request)
    actor_uid = _get_user_id(request)

    if kind == "org" and org_id:
        _require_org_role(request, org_id, orgs_mod.ROLE_EDITOR)
        owner_id = ""
        scope_org_id = org_id
    else:
        _require_owner(request)
        _check_corpus_limit(request)
        owner_id = actor_uid if _is_cloud() else ""
        scope_org_id = ""

    # Resolve workspace-aware default for access_level.
    resolved_access = req.access_level
    if resolved_access is None:
        resolved_access = "private" if scope_org_id else "public"

    try:
        corpus = create_corpus(
            req.name, description=req.description, author_name=req.author_name,
            tags=req.tags, access_level=resolved_access, language=req.language,
            owner_id=owner_id, org_id=scope_org_id,
        )
    except DuplicateCorpusName as dup:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_corpus_name",
                "message": f"A corpus named '{dup.name}' already exists in this workspace.",
                "existing_corpus_id": dup.existing_id,
                "name": dup.name,
            },
        )

    if scope_org_id:
        orgs_mod.log_audit(
            "corpus.create", org_id=scope_org_id, actor_user_id=actor_uid,
            resource_type="corpus", resource_id=corpus["id"],
            metadata={"name": corpus["name"], "access_level": corpus.get("access_level")},
            ip_addr=_client_ip(request),
        )
    # Materialize the manifest doc immediately so it's pinned first in Wiki
    # from the moment the corpus exists. Auto-fill runs later (after first
    # ingestion) and will refresh the doc content in place.
    try:
        from noosphere.core.manifest_doc import ensure_manifest_doc
        ensure_manifest_doc(corpus["id"])
    except Exception:
        pass
    # Push the new non-private corpus to the registry so it's discoverable
    # immediately (fixes the stale-registry gap: previously only the serve
    # startup snapshot was registered, so runtime creates were invisible
    # until restart). BackgroundTasks keeps the response latency down.
    if (req.access_level or "public") != "private":
        background_tasks.add_task(_safe_resync_registry)
    return corpus


def _safe_update_corpus_embeddings_batch(corpus_ids: list[str]):
    """BackgroundTasks wrapper — embeds N corpora in a SINGLE API call.

    Replaces the previous one-task-per-corpus pattern that fired N
    sequential embedder requests in rapid succession (and consumed N
    rate-limit slots). With Gemini free-tier RPM caps, that fan-out was
    the actual reason production stayed at embedded=0 — every backfill
    request burned through the per-minute budget on probes alone.
    """
    if not corpus_ids:
        return
    try:
        from noosphere.core.corpus_embedding import update_corpus_embeddings_batch
        result = update_corpus_embeddings_batch(corpus_ids)
        if result["succeeded"]:
            logger.info("[corpus_embed] batch backfilled %d/%d (embedder=%s)",
                        len(result["succeeded"]), len(corpus_ids), result.get("embedder"))
        if result["failed"]:
            sample = result["failed"][0]
            logger.warning("[corpus_embed] batch had %d failures (sample: %s: %s)",
                           len(result["failed"]), sample.get("id"), sample.get("error"))
    except Exception as e:
        logger.warning("[corpus_embed] batch embedding raised: %s", e)


@router.post("/admin/recompute-embeddings")
async def api_admin_recompute_embeddings(request: Request, limit: int = 50):
    """Synchronously recompute corpus profile embeddings, returning a
    per-corpus diagnostic. Designed for "the graph has no edges, why?"
    debugging — bypasses BackgroundTasks (so we know if those are the
    bottleneck) and surfaces the real exception per corpus instead of
    swallowing it.

    Owner-only. Picks rows where corpus_vector IS NULL OR dirty, capped
    at `limit` per call (default 50) so a 500-corpus deployment doesn't
    block a request for minutes.

    Response shape:
      {
        "attempted": 8,
        "succeeded": 6,
        "failed": 2,
        "results": [
          {"id": "abc123", "name": "AI design", "status": "success"},
          {"id": "def456", "name": "Notes", "status": "failed",
           "error": "All embedding providers failed: gemini: 429 ..."}
        ]
      }
    """
    _require_owner(request)
    limit = max(1, min(200, int(limit)))
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name FROM corpora "
        "WHERE corpus_vector IS NULL OR corpus_vector_dirty_since IS NOT NULL "
        "ORDER BY (corpus_vector IS NULL) DESC, updated_at DESC "
        "LIMIT ?",
        (limit,),
    ).fetchall()
    name_by_id = {r["id"]: r["name"] for r in rows}
    if not rows:
        return {"attempted": 0, "succeeded": 0, "failed": 0,
                "embedder": None, "results": []}

    # Use the batched helper — one API call carries every corpus,
    # so a backfill of 50 corpora is 1 RPM hit, not 50.
    from noosphere.core.corpus_embedding import update_corpus_embeddings_batch
    batch = update_corpus_embeddings_batch([r["id"] for r in rows])

    succ_set = set(batch["succeeded"])
    fail_by_id = {f["id"]: f["error"] for f in batch["failed"]}
    results = []
    for r in rows:
        cid = r["id"]
        if cid in succ_set:
            results.append({"id": cid, "name": name_by_id[cid], "status": "success"})
        elif cid in fail_by_id:
            err = fail_by_id[cid]
            status = "skipped" if err == "empty profile text" else "failed"
            results.append({"id": cid, "name": name_by_id[cid],
                            "status": status, "error": err})
        else:
            # Shouldn't happen — batch should account for every input.
            results.append({"id": cid, "name": name_by_id[cid],
                            "status": "failed", "error": "missing from batch result"})

    return {
        "attempted": len(rows),
        "succeeded": len(succ_set),
        "failed": len(batch["failed"]),
        "embedder": batch.get("embedder"),
        "results": results,
    }


@router.get("/corpora/network")
async def api_corpus_network(request: Request, background_tasks: BackgroundTasks):
    # Noosphere = the world. Every registered corpus surfaces as a node
    # regardless of access_level — visibility of the *node* is universal,
    # access to *content* is what's gated. Private corpora appear with
    # only id/name/tags so the graph stays complete; paid corpora carry
    # `pricing` / `accepts` / `checkout_url` so both humans (Stripe
    # Checkout) and agents (x402 challenge) can act without first being
    # bounced by a 402.
    corpora = list_corpora(include_private=True)
    if _is_cloud():
        corpora = [c for c in corpora if c.get("owner_id") or c.get("org_id")]
    is_owner = _is_owner_request(request)
    # Lazy backfill: any corpus without a profile embedding yet gets one
    # computed in the background. The current response uses whatever
    # tag-only links are computable; the next /network call will pick up
    # the freshly-embedded vectors and show semantic edges. Cost is
    # bounded — each corpus only gets embedded once until its profile
    # fields change. Cap per-request to avoid hammering the embedder
    # API on a fresh deployment with hundreds of pre-existing corpora;
    # subsequent requests catch up.
    #
    # The corpus dicts here have `corpus_vector` stripped (it's raw
    # bytes that break FastAPI's encoder), so we can't read the column
    # off of them directly — query the storage side with a single SELECT.
    # Per-cycle cap on backfill. Lowered from 8 → 3 because the original
    # 8 was a cost-bound argument ("don't trash the embedder API on a
    # 500-corpus deployment") but production hit Gemini free-tier RPM
    # before we even had 8 corpora. With the new batched embed (one API
    # call carries the whole cap) the cost argument is moot anyway —
    # 3 is just enough to make steady progress on a fresh deployment
    # without burning a whole RPM slot on a single graph view, leaving
    # room for the occasional dirty-refresh.
    _BACKFILL_CAP = 3
    try:
        _ids = [c["id"] for c in corpora]
        if _ids:
            _conn = get_conn()
            _placeholders = ",".join(["?"] * len(_ids))
            # Pick up two flavours in one pass:
            #   - corpus_vector IS NULL          → never embedded yet
            #   - corpus_vector_dirty_since SET  → content shifted since
            #     the last embed (doc add / new entities / manifest
            #     regen) and the vector is now stale.
            # Order NULLs first so a brand-new corpus on a busy node
            # doesn't get starved by a queue of stale-but-already-embedded
            # ones — a fresh corpus appearing as a disconnected dot is
            # the worse UX failure.
            _rows = _conn.execute(
                f"SELECT id FROM corpora "
                f"WHERE id IN ({_placeholders}) "
                f"AND (corpus_vector IS NULL OR corpus_vector_dirty_since IS NOT NULL) "
                f"ORDER BY (corpus_vector IS NULL) DESC "
                f"LIMIT {_BACKFILL_CAP}",
                tuple(_ids),
            ).fetchall()
            # Dispatch a SINGLE batched task — one embedder API call
            # carries all rows. Avoids the previous per-row task fan-out
            # that hit RPM limits even with 8 inputs.
            ids_to_embed = [_r["id"] for _r in _rows]
            if ids_to_embed:
                background_tasks.add_task(_safe_update_corpus_embeddings_batch, ids_to_embed)
    except Exception as _bf_err:
        logger.debug("backfill scan skipped: %s", _bf_err)
    nodes = []
    for c in corpora:
        access_level = c.get("access_level", "public")
        tags = c.get("tags", [])
        if isinstance(tags, str):
            try:
                tags = _json.loads(tags)
            except Exception:
                tags = []
        tokens = []
        for t in tags:
            tokens.extend([x.strip().lower() for x in t.replace(",", " ").split() if x.strip()])
        name = c["name"]
        initials = "".join(w[0].upper() for w in name.split()[:2]) if name else "?"

        # Private + non-owner: emit a minimal locked node so the graph
        # stays complete but content metadata (description, doc counts,
        # author, status, etc.) doesn't leak. Tags stay so the node still
        # finds its semantic neighborhood.
        if access_level == "private" and not is_owner:
            nodes.append({
                "id": c["id"], "name": name,
                "tags": tags, "tokens": tokens, "initials": initials,
                "access_level": "private",
                "kind": "local",
            })
            continue

        node = {
            "id": c["id"], "name": name, "slug": c.get("slug", ""),
            "description": c.get("description", ""), "author": c.get("author_name", ""),
            "tags": tags, "tokens": tokens, "initials": initials,
            "document_count": c.get("document_count", 0),
            "chunk_count": c.get("chunk_count", 0),
            "word_count": c.get("word_count", 0),
            "status": c.get("status", "draft"),
            "access_level": access_level,
            "task_types": c.get("task_types", []),
            "autonomy_level": c.get("autonomy_level", 0),
            "kind": "local",
        }

        # Paid: ship pricing + x402 accepts + Stripe checkout pointer so
        # the caller can act without first hitting the 402 gate. Humans
        # use checkout_url (Stripe Checkout); agents pick from accepts
        # (x402 v1 spec) and re-present `X-PAYMENT`.
        if access_level == "paid":
            try:
                pricing_raw = c.get("pricing_json")
                if pricing_raw:
                    pricing = _json.loads(pricing_raw) if isinstance(pricing_raw, str) else pricing_raw
                    if isinstance(pricing, dict):
                        node["pricing"] = pricing
            except Exception:
                pass
            try:
                from noosphere.core.agent_payments import build_x402_challenge
                resource = f"/api/v1/corpora/{c['id']}"
                challenge = build_x402_challenge(c, resource=resource)
                accepts = challenge.get("accepts") or []
                if accepts:
                    node["accepts"] = accepts
            except Exception:
                pass
            node["checkout_url"] = f"/api/v1/corpora/{c['id']}/checkout"

        nodes.append(node)

    # Merge in remote corpora from registered_corpora — populated by the
    # registry layer when this node federates with a Noosphere registry.
    # These are public-by-construction (registries only accept non-private
    # entries) but we filter again defensively. They render as additional
    # nodes in the graph; tag-overlap edges form naturally between local
    # and remote tokens. No semantic edges (we don't have remote vectors).
    # IDs are prefixed `r/<endpoint>/<corpus_id>` so they don't collide
    # with local IDs and the frontend can detect "this is a remote node,
    # don't try to /corpus/:id navigate" on click.
    try:
        _conn = get_conn()
        remote_rows = _conn.execute(
            "SELECT * FROM registered_corpora WHERE access_level != 'private' "
            "ORDER BY updated_at DESC"
        ).fetchall()
        # Avoid emitting a remote node that's actually our own (this node's
        # corpora may be in the registry too if we're configured to register).
        local_corpus_ids = {c["id"] for c in corpora}
        for r in remote_rows:
            rd = dict(r)
            if rd.get("corpus_id") in local_corpus_ids:
                continue
            r_tags = rd.get("tags") or []
            if isinstance(r_tags, str):
                try:
                    r_tags = _json.loads(r_tags)
                except Exception:
                    r_tags = []
            r_task_types = rd.get("task_types") or []
            if isinstance(r_task_types, str):
                try:
                    r_task_types = _json.loads(r_task_types)
                except Exception:
                    r_task_types = []
            r_tokens = []
            for t in r_tags:
                r_tokens.extend([x.strip().lower() for x in str(t).replace(",", " ").split() if x.strip()])
            r_name = rd.get("name") or "Untitled"
            r_initials = "".join(w[0].upper() for w in r_name.split()[:2]) if r_name else "?"
            nodes.append({
                "id": f"r/{rd.get('node_endpoint', '')}/{rd.get('corpus_id', '')}",
                "name": r_name,
                "slug": rd.get("slug") or "",
                "description": rd.get("description") or "",
                "author": rd.get("author") or "",
                "tags": r_tags, "tokens": r_tokens, "initials": r_initials,
                "document_count": rd.get("document_count", 0),
                "chunk_count": rd.get("chunk_count", 0),
                "word_count": rd.get("word_count", 0),
                "status": rd.get("status", "draft"),
                "access_level": rd.get("access_level", "public"),
                "task_types": r_task_types,
                "autonomy_level": rd.get("autonomy_level", 0),
                "kind": "remote",
                "node_endpoint": rd.get("node_endpoint") or "",
                "remote_corpus_id": rd.get("corpus_id") or "",
            })
    except Exception as _re:
        logger.debug("registered_corpora merge skipped: %s", _re)

    # Edge computation runs in two layered passes so the graph stays
    # connected regardless of which signals are populated on which corpora:
    #
    #   Layer 1 — semantic (corpus_vector cosine similarity).
    #     Strong signal. Any pair where both corpora have a profile
    #     embedding contributes an edge if cosine >= floor. This is
    #     where a fresh node with no tags still gets meaningful links —
    #     the profile vector is built from name/description/entities/etc.
    #     so even an empty corpus has a coherent semantic neighborhood.
    #
    #   Layer 2 — explicit tag overlap (the original signal).
    #     Always added for any pair sharing at least one tag token,
    #     marked as 'kind=tag' so the frontend can render it
    #     differently from semantic edges (Graphene-style: solid for
    #     human-curated, dashed for AI-inferred). Tag edges supersede
    #     a semantic edge between the same pair if both exist.
    #
    # Top-K=4 per node is enforced on the semantic layer to prevent
    # high-density clusters (similar embeddings everywhere) from
    # collapsing the graph into a hairball — same trick Feynman uses.
    SEM_FLOOR = 0.45
    SEM_TOP_K = 4

    edges: dict[tuple[str, str], dict] = {}

    # ── Layer 1: semantic ──────────────────────────────────────────
    try:
        from noosphere.core.corpus_embedding import load_corpus_vectors
        import numpy as _np
        node_ids = [n["id"] for n in nodes]
        vec_rows = load_corpus_vectors(node_ids)
        if len(vec_rows) >= 2:
            # Stack into NxD matrix, normalise rows so a single matmul
            # gives the full pairwise cosine matrix in one shot.
            id_index = {v["id"]: i for i, v in enumerate(vec_rows)}
            mat = _np.stack([
                v["vec"] / (v["norm"] or 1.0) for v in vec_rows
            ]).astype(_np.float32)
            sims = mat @ mat.T  # NxN cosine
            n = len(vec_rows)
            # Per-node top-K (excluding self), then dedupe across the
            # two endpoints so we don't double-emit a pair.
            kept_pairs: set[tuple[int, int]] = set()
            for i in range(n):
                row = sims[i].copy()
                row[i] = -1.0  # exclude self
                # argpartition is faster than a full sort for top-K.
                k = min(SEM_TOP_K, n - 1)
                idxs = _np.argpartition(-row, k - 1)[:k]
                for j in idxs:
                    if row[j] < SEM_FLOOR:
                        continue
                    a, b = (int(i), int(j)) if i < j else (int(j), int(i))
                    kept_pairs.add((a, b))
            for a, b in kept_pairs:
                src_id = vec_rows[a]["id"]
                tgt_id = vec_rows[b]["id"]
                if src_id not in id_index or tgt_id not in id_index:
                    continue
                key = (src_id, tgt_id)
                strength = float(sims[a, b])
                edges[key] = {
                    "source": src_id, "target": tgt_id,
                    "strength": round(strength, 4),
                    "kind": "semantic",
                }
    except Exception as _sem_err:
        # Embedding pipeline failure must never break /network — graph
        # falls back to tag-only links and the user still sees something.
        logger.debug("semantic-link computation skipped: %s", _sem_err)

    # ── Layer 2: tag overlap ───────────────────────────────────────
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = set(nodes[i]["tokens"]) & set(nodes[j]["tokens"])
            if not shared:
                continue
            src_id, tgt_id = nodes[i]["id"], nodes[j]["id"]
            key = (src_id, tgt_id)
            edges[key] = {
                "source": src_id, "target": tgt_id,
                "strength": float(len(shared)),
                "kind": "tag",
                "shared_tags": list(shared),
            }

    return {"nodes": nodes, "links": list(edges.values())}


@router.get("/corpora/{corpus_id}")
async def api_get_corpus(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    corpus["source_composition"] = source_composition(corpus["id"])
    return corpus


# ── llms.txt / llms-full.txt (https://llmstxt.org) ────────────────────
# Per-corpus static-text views for any LLM/agent that wants to read the
# corpus in one fetch — no API integration, no exporter. Reuses the same
# access gating as the JSON corpus endpoint; private corpora 403.

@router.get("/corpora/{corpus_id}/llms.txt")
async def api_llms_index(corpus_id: str, request: Request):
    """Markdown index of the corpus — title, description, document list."""
    from fastapi.responses import PlainTextResponse
    from noosphere.core.llmstxt import render_llms_index
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    docs = get_documents(corpus["id"])
    text = render_llms_index(corpus, docs, base_path="/api/v1")
    log_access(request, corpus_id=corpus["id"], surface="corpus_llms")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


@router.get("/corpora/{corpus_id}/llms-full.txt")
async def api_llms_full(corpus_id: str, request: Request):
    """Full-text dump — corpus header followed by every published document inlined."""
    from fastapi.responses import PlainTextResponse
    from noosphere.core.llmstxt import render_llms_full
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    docs = get_documents(corpus["id"])
    text = render_llms_full(corpus, docs)
    log_access(request, corpus_id=corpus["id"], surface="corpus_llms_full")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")


def _corpus_source_kind_breakdown(corpus_id: str) -> dict[str, int]:
    """Count documents per source_kind for a corpus.

    Excludes `source_kind='system'` — auto-generated metadata (manifest doc)
    doesn't count as user content for access-gate / pricing logic, and
    shouldn't show up in access summary totals either.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT source_kind, COUNT(*) as n FROM documents "
        "WHERE corpus_id=? AND COALESCE(source_kind,'user_original') != 'system' "
        "GROUP BY source_kind",
        (corpus_id,),
    ).fetchall()
    return {r["source_kind"] or "user_original": r["n"] for r in rows}


def _require_originals_for_public_access(corpus_id: str, new_access_level: str) -> None:
    """Block publish / paid-access when the corpus has documents but zero originals.

    Empty corpora are allowed through (user may be configuring before ingest).
    Corpora with only external content are blocked — external callers would
    receive nothing since imported external material is filtered out.
    """
    if new_access_level not in ("public", "paid", "token"):
        return
    counts = _corpus_source_kind_breakdown(corpus_id)
    total = sum(counts.values())
    if total == 0:
        return
    originals = counts.get("user_original", 0) + counts.get("user_capture", 0)
    if originals == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot enable external access: this corpus contains only "
                "external material. External callers would receive an empty "
                "response since imported external content is filtered out. "
                "Add at least one user-originated document first."
            ),
        )


@router.get("/corpora/{corpus_id}/access-summary")
async def api_access_summary(corpus_id: str, request: Request):
    """Breakdown of documents by source_kind — used by publish/paid confirm flows.

    Returns counts per source_kind plus what each class will look like to
    different caller types (owner vs external).
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    counts = _corpus_source_kind_breakdown(corpus["id"])
    total = sum(counts.values())
    originals = counts.get("user_original", 0) + counts.get("user_capture", 0)
    return {
        "total": total,
        "originals": originals,
        "by_source_kind": counts,
        "can_enable_external_access": originals > 0,
        "visibility": {
            "owner": total,
            "external": originals,
        },
    }


@router.patch("/corpora/{corpus_id}")
async def api_update_corpus(corpus_id: str, req: UpdateCorpusRequest, request: Request, background_tasks: BackgroundTasks):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    # The pydantic model uses license_ (license is reserved), but the DB
    # column is "license". Rename on the way in so update_corpus's allow-list
    # accepts it.
    if "license_" in updates:
        updates["license"] = updates.pop("license_")
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    new_access_level = updates.get("access_level")
    cur_access = corpus.get("access_level")
    if new_access_level and new_access_level != cur_access:
        _require_originals_for_public_access(corpus_id, new_access_level)
    result = update_corpus(corpus_id, **updates)
    # Access-level demotion to private should not silently leave existing
    # access tokens working — revoke them so the user's private flip is a
    # real boundary, not just a UI label change.
    if new_access_level == "private" and cur_access in ("public", "token", "paid"):
        try:
            conn = get_conn()
            conn.execute("DELETE FROM access_tokens WHERE corpus_id=?", (corpus_id,))
            conn.commit()
        except Exception:
            pass
    # Keep the pinned manifest doc in sync with the canonical fields so the
    # README-as-doc view reflects edits immediately (description, tags,
    # access_level, calibration_policy, etc.).
    manifest_affecting = {
        "name", "description", "tags", "access_level",
        "task_types", "samples", "calibration_policy", "autonomy_level",
    }
    if updates.keys() & manifest_affecting:
        try:
            from noosphere.core.manifest_doc import ensure_manifest_doc, refresh_manifest_doc
            ensure_manifest_doc(corpus_id)
            refresh_manifest_doc(corpus_id)
        except Exception:
            pass
    # Registry resync: any field change touches the registered record. The
    # registry endpoint reconciles (adds/updates/removes) based on the full
    # snapshot, so flipping access_level private↔public both work — a now-
    # private corpus is just absent from the next snapshot.
    registry_affecting = {
        "name", "description", "tags", "access_level", "author_name",
        "task_types", "autonomy_level", "calibration_policy",
    }
    if updates.keys() & registry_affecting:
        background_tasks.add_task(_safe_resync_registry)
    if corpus.get("org_id"):
        action = "access.change" if new_access_level and new_access_level != corpus.get("access_level") else "corpus.update"
        orgs_mod.log_audit(
            action, org_id=corpus["org_id"], actor_user_id=_get_user_id(request),
            resource_type="corpus", resource_id=corpus_id,
            metadata={"fields": list(updates.keys())},
            ip_addr=_client_ip(request),
        )
    return result


@router.delete("/corpora/{corpus_id}")
async def api_delete_corpus(corpus_id: str, request: Request, background_tasks: BackgroundTasks):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    actor_uid = _get_user_id(request)
    delete_corpus(corpus_id)
    if corpus.get("org_id"):
        orgs_mod.log_audit(
            "corpus.delete", org_id=corpus["org_id"], actor_user_id=actor_uid,
            resource_type="corpus", resource_id=corpus_id,
            metadata={"name": corpus.get("name")},
            ip_addr=_client_ip(request),
        )
    # The next snapshot won't include this corpus, so the registry's
    # reconcile step deletes its record.
    background_tasks.add_task(_safe_resync_registry)
    return {"status": "deleted"}


def _safe_resync_registry() -> None:
    """Wrap resync_registry so a registry outage never surfaces as an
    exception in a background task (which would spam logs). Log-only."""
    try:
        from noosphere.core.registry import resync_registry
        resync_registry()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Background registry resync failed: %s", e)


# ── Documents ──

@router.get("/corpora/{corpus_id}/documents")
async def api_list_documents(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    # Lazy-backfill the manifest document for corpora that predate the
    # README-as-doc feature. Only the owner triggers this (creator view);
    # read-only external callers fetch whatever's already there to avoid
    # write-on-read races in a hot multi-agent path.
    try:
        if _is_owner_request(request):
            from noosphere.core.manifest_doc import ensure_manifest_doc
            ensure_manifest_doc(corpus["id"])
    except Exception:
        pass
    return get_documents(corpus["id"])


@router.get("/corpora/{corpus_id}/documents/{doc_id}")
async def api_get_document(corpus_id: str, doc_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


_VALID_SOURCE_KINDS = ("user_original", "external_public", "external_subscription")


@router.patch("/corpora/{corpus_id}/documents/{doc_id}")
async def api_update_document(corpus_id: str, doc_id: str, req: UpdateDocumentRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "source_kind" in updates and updates["source_kind"] not in _VALID_SOURCE_KINDS:
        raise HTTPException(status_code=400, detail=f"source_kind must be one of {_VALID_SOURCE_KINDS}")
    result = update_document(doc_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found")
    return result


@router.delete("/corpora/{corpus_id}/documents/{doc_id}")
async def api_delete_document(corpus_id: str, doc_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


# ── File upload ──

from noosphere.core.ingest import (
    _extract_pdf_text, _extract_docx_text, _extract_csv_text, _extract_json_text,
)


@router.post("/corpora/{corpus_id}/upload")
async def api_upload_files(
    corpus_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    source_kind: str = Form("user_original"),
):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    contributor_uid = _get_user_id(request)
    # Uploads share the "index" bucket because the client always fires a
    # follow-up /index. The follow-up now only charges when embedding work
    # actually ran (see api_index_corpus), so the net per-upload cost stays
    # at 1 quota unit in the typical case — no double-charging.
    _check_quota(request, "index")
    _check_document_limit(request, corpus["id"])
    results = []
    errors: list[dict] = []
    for f in files:
        fname = f.filename or "Untitled"
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        raw = await f.read()

        try:
            if ext == "pdf":
                body = _extract_pdf_text(raw)
                title = fname.rsplit(".", 1)[0]
                metadata, doc_type = {}, "paper"
            elif ext == "docx":
                body = _extract_docx_text(raw)
                title = fname.rsplit(".", 1)[0]
                metadata, doc_type = {}, "doc"
            elif ext == "csv":
                content = raw.decode("utf-8", errors="replace")
                body = _extract_csv_text(content)
                title = fname.rsplit(".", 1)[0]
                metadata, doc_type = {}, "data"
            elif ext in ("json", "jsonl"):
                content = raw.decode("utf-8", errors="replace")
                if ext == "jsonl":
                    import json as _j
                    lines = [_j.loads(line) for line in content.strip().splitlines() if line.strip()]
                    body = _extract_json_text(_json.dumps(lines))
                else:
                    body = _extract_json_text(content)
                title = fname.rsplit(".", 1)[0]
                metadata, doc_type = {}, "data"
            else:
                content = raw.decode("utf-8", errors="replace")
                if not content.strip():
                    errors.append({"file": fname, "error": "file is empty"})
                    continue
                from noosphere.core.ingest import _extract_markdown_metadata, _extract_markdown_title
                metadata, body = _extract_markdown_metadata(content)
                title = metadata.get("title") or _extract_markdown_title(body) or fname.rsplit(".", 1)[0]
                doc_type = "doc" if ext in ("md", "markdown", "html", "htm") else "note"
        except Exception as e:
            errors.append({"file": fname, "error": f"could not extract text: {e}"})
            continue

        if not body or not body.strip():
            errors.append({"file": fname, "error": "no readable text extracted (empty or unsupported encoding)"})
            continue

        # PDFs and DOCX files extract junk when the source is corrupted, image-only,
        # or password-protected — yielding a few stray words from headers/watermarks.
        # Reject anything under 10 words from binary formats so the user sees the
        # failure instead of finding a useless "document" later. Plain-text formats
        # have no floor — short notes are legitimate.
        word_count = len(body.split())
        if ext in ("pdf", "docx") and word_count < 10:
            errors.append({
                "file": fname,
                "error": f"only {word_count} words extracted — likely corrupted, scanned-image-only, or password-protected",
            })
            continue

        tags_str = metadata.get("tags", "") if isinstance(metadata, dict) else ""
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

        doc = ingest_text(
            corpus["id"], title=title, content=body, doc_type=doc_type,
            source_kind=source_kind,
            date=metadata.get("date", "") if isinstance(metadata, dict) else "",
            tags=tags, metadata=metadata if isinstance(metadata, dict) else {},
            contributor_user_id=contributor_uid,
        )
        results.append(doc)

    if results:
        _track_usage(request, "index")
        if corpus.get("org_id"):
            for d in results:
                orgs_mod.log_audit(
                    "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
                    resource_type="document", resource_id=d["id"],
                    metadata={"corpus_id": corpus["id"], "title": d["title"], "source": "upload"},
                    ip_addr=_client_ip(request),
                )
    return {
        "uploaded": len(results),
        "failed": len(errors),
        "documents": results,
        "errors": errors,
    }


# ── URL ingestion ──

@router.post("/corpora/{corpus_id}/ingest-url")
async def api_ingest_url(corpus_id: str, req: IngestURLRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "ingest_url")
    _check_document_limit(request, corpus["id"])
    contributor_uid = _get_user_id(request)
    try:
        doc = ingest_url(
            corpus["id"], req.url,
            doc_type=req.doc_type, source_kind=req.source_kind,
            contributor_user_id=contributor_uid,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    _track_usage(request, "ingest_url")
    if corpus.get("org_id"):
        orgs_mod.log_audit(
            "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
            resource_type="document", resource_id=doc["id"],
            metadata={"corpus_id": corpus["id"], "url": req.url, "source": "url"},
            ip_addr=_client_ip(request),
        )
    return doc


@router.post("/corpora/{corpus_id}/ingest-urls")
async def api_ingest_urls_bulk(corpus_id: str, req: IngestUrlsRequest, request: Request):
    """Batch URL ingestion (lower friction than one request per page)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if len(req.urls) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 URLs per request")
    from noosphere.core.knowledge_growth import ingest_urls_bulk

    contributor_uid = _get_user_id(request)
    try:
        result = ingest_urls_bulk(
            corpus["id"], req.urls,
            doc_type=req.doc_type, source_kind=req.source_kind,
            contributor_user_id=contributor_uid,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if corpus.get("org_id"):
        for d in (result.get("results") or result.get("documents") or []):
            doc_id = d.get("id") if isinstance(d, dict) else None
            if not doc_id:
                continue
            orgs_mod.log_audit(
                "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
                resource_type="document", resource_id=doc_id,
                metadata={"corpus_id": corpus["id"], "source": "ingest-urls"},
                ip_addr=_client_ip(request),
            )
    return result


@router.post("/corpora/{corpus_id}/ingest-feed")
async def api_ingest_feed(corpus_id: str, req: IngestFeedRequest, request: Request):
    """Ingest new entries from an RSS or Atom feed."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "ingest_feed")
    from noosphere.core.knowledge_growth import ingest_rss_feed

    contributor_uid = _get_user_id(request)
    try:
        result = ingest_rss_feed(
            corpus["id"], req.feed_url.strip(),
            max_items=req.max_items,
            contributor_user_id=contributor_uid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    _track_usage(request, "ingest_feed")
    if corpus.get("org_id"):
        for d in (result.get("documents") or []):
            doc_id = d.get("id") if isinstance(d, dict) else None
            if not doc_id:
                continue
            orgs_mod.log_audit(
                "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
                resource_type="document", resource_id=doc_id,
                metadata={"corpus_id": corpus["id"], "feed_url": req.feed_url, "source": "rss"},
                ip_addr=_client_ip(request),
            )
    return result


@router.post("/corpora/{corpus_id}/capture")
async def api_capture(corpus_id: str, req: CaptureRequest, request: Request):
    """Persist text into the corpus (e.g. assistant reply from chat)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import save_capture

    contributor_uid = _get_user_id(request)
    try:
        result = save_capture(
            corpus["id"],
            content=req.content,
            title=req.title,
            question=req.question,
            session_id=req.session_id or "",
            contributor_user_id=contributor_uid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if corpus.get("org_id"):
        doc_id = result.get("id") if isinstance(result, dict) else None
        orgs_mod.log_audit(
            "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
            resource_type="document", resource_id=doc_id or "",
            metadata={"corpus_id": corpus["id"], "source": "capture"},
            ip_addr=_client_ip(request),
        )
    return result


# ── Archive imports (Twitter / Notion) ──

async def _save_upload_to_temp(file: UploadFile, suffix: str = ".zip") -> str:
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
    finally:
        tmp.close()
    return tmp.name


@router.post("/corpora/{corpus_id}/import/twitter")
async def api_import_twitter(corpus_id: str, request: Request, file: UploadFile = File(...)):
    """Import a Twitter/X data export ZIP. Tweets are ingested as user_original."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a .zip archive")
    path = await _save_upload_to_temp(file)
    contributor_uid = _get_user_id(request)
    try:
        from noosphere.core.importers import import_twitter_archive
        result = import_twitter_archive(corpus["id"], path, contributor_user_id=contributor_uid)
        if corpus.get("org_id"):
            orgs_mod.log_audit(
                "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
                resource_type="corpus", resource_id=corpus["id"],
                metadata={"source": "twitter-archive", "imported": result.get("imported", 0)},
                ip_addr=_client_ip(request),
            )
        return result
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@router.post("/corpora/{corpus_id}/import/notion")
async def api_import_notion(corpus_id: str, request: Request, file: UploadFile = File(...)):
    """Import a Notion workspace export ZIP. Pages are ingested as user_original."""
    corpus = _resolve_corpus(corpus_id)
    contributor_uid = _get_user_id(request)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a .zip archive")
    path = await _save_upload_to_temp(file)
    try:
        from noosphere.core.importers import import_notion_export
        result = import_notion_export(corpus["id"], path, contributor_user_id=contributor_uid)
        if corpus.get("org_id"):
            orgs_mod.log_audit(
                "doc.ingest", org_id=corpus["org_id"], actor_user_id=contributor_uid,
                resource_type="corpus", resource_id=corpus["id"],
                metadata={"source": "notion-archive", "imported": result.get("imported", 0)},
                ip_addr=_client_ip(request),
            )
        return result
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


@router.get("/corpora/{corpus_id}/writeback")
async def api_writeback(corpus_id: str, request: Request, since: str = ""):
    """Return Noosphere-synthesized entity + concept pages as a markdown
    payload for CLI sync clients to mirror into a user's vault.

    Owner-only. `since` is an optional ISO8601 timestamp for incremental
    polling — the CLI tracks it in `<vault>/__noosphere/.sync-state.json`
    between runs so the server only sends what's changed.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.writeback import compute_writeback
    return compute_writeback(corpus["id"], since=since or None)


@router.get("/corpora/{corpus_id}/sync/state")
async def api_sync_state(corpus_id: str, request: Request):
    """Return the server's current view of synced documents (path →
    content_hash). The Obsidian plugin uses this to diff against the
    local vault and only upload files that differ.

    Owner-only. Works regardless of whether the client and server share
    a filesystem — that's the whole point of cloud-safe sync.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.ingest import corpus_sync_state
    return corpus_sync_state(corpus["id"])


class SyncUpsertRequest(BaseModel):
    """Single-document push from an HTTP sync client."""
    path: str
    content: str
    format: str = "obsidian"


@router.post("/corpora/{corpus_id}/sync/upsert")
async def api_sync_upsert(corpus_id: str, request: Request, body: SyncUpsertRequest):
    """Upload one document. Path-keyed — re-uploading with the same content
    is a no-op (returns action=unchanged). For initial sync the client
    calls this once per file; for watch mode, once per change event."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])
    from noosphere.core.ingest import upsert_document_by_path
    try:
        return upsert_document_by_path(
            corpus["id"], path=body.path, content=body.content, format=body.format
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/corpora/{corpus_id}/sync/doc")
async def api_sync_doc_delete(corpus_id: str, request: Request, path: str = ""):
    """Delete a synced document by its vault-relative path. Used when the
    user deletes or renames a file in their vault while the plugin has
    prune enabled."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if not path.strip():
        raise HTTPException(status_code=400, detail="`path` query param required")
    from noosphere.core.ingest import delete_document_by_path
    return delete_document_by_path(corpus["id"], path)


class SyncLocalRequest(BaseModel):
    """Drive sync_directory from an HTTP caller (the Obsidian plugin).

    ``path`` is a filesystem path the server can read — for the plugin's
    primary use case the user runs Noosphere self-hosted on the same
    machine as Obsidian so both share the vault folder. Cloud Noosphere
    would need a file-upload variant; scoped out for v0.1.
    """
    path: str
    format: str = "obsidian"
    prune: bool = False
    writeback: bool = True


@router.post("/corpora/{corpus_id}/sync-local")
async def api_sync_local(corpus_id: str, request: Request, body: SyncLocalRequest):
    """Trigger a sync of a local-filesystem directory into this corpus.

    Mirrors what the ``noosphere sync`` CLI does, but exposed as an HTTP
    endpoint so the Obsidian plugin can kick it off with one click. The
    server must have read access to ``body.path`` — this is the
    self-hosted co-located setup (Obsidian + Noosphere on the same
    machine). For cloud Noosphere, a file-upload variant is planned.

    Owner-only. Returns sync counts + writeback result when enabled.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])

    from pathlib import Path
    vault = Path(body.path).expanduser()
    if not vault.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a readable directory on the server: {body.path}")

    from noosphere.core.ingest import sync_directory
    from noosphere.core.indexer import index_corpus

    try:
        result = sync_directory(corpus["id"], str(vault), prune=body.prune, format=body.format)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    index_result = None
    if result.get("new") or result.get("updated"):
        try:
            index_result = index_corpus(corpus["id"])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Index after sync-local failed: %s", e)

    writeback_result = None
    if body.writeback:
        try:
            from noosphere.cli.main import _writeback_to_vault
            writeback_result = _writeback_to_vault(corpus["id"], str(vault))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Writeback after sync-local failed: %s", e)

    return {
        "sync": result,
        "index": {"chunk_count": index_result.get("chunk_count")} if index_result else None,
        "writeback": writeback_result,
    }


@router.post("/corpora/{corpus_id}/import/obsidian")
async def api_import_obsidian(corpus_id: str, request: Request, file: UploadFile = File(...)):
    """Import an Obsidian vault (zipped folder of .md files).

    Preserves folder paths, YAML frontmatter, `#hashtags`, and `[[wikilinks]]`
    on every note. Notes land as source_kind=user_original — the user owns
    their vault. First-class entry point for Obsidian users bringing an
    existing vault into the network.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_document_limit(request, corpus["id"])
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a .zip archive of your vault folder")
    path = await _save_upload_to_temp(file)
    try:
        from noosphere.core.importers import import_obsidian_vault
        return import_obsidian_vault(corpus["id"], path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ── Entity extraction (Phase 0.5) ──


class ExtractEntitiesRequest(BaseModel):
    limit: int = 50


@router.get("/corpora/{corpus_id}/entities")
async def api_list_entities(corpus_id: str, request: Request, kind: Optional[str] = None):
    """List entities in the corpus, annotated with mention counts."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.entities import list_entities
    return {"entities": list_entities(corpus["id"], kind=kind)}


@router.post("/corpora/{corpus_id}/entities/{entity_id}/compile")
async def api_compile_entity(corpus_id: str, entity_id: str, request: Request):
    """LLM-compile a 'compiled truth' summary for an entity (one page per person/company)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.entities import compile_entity_note, get_entity
    ent = get_entity(entity_id)
    if not ent or ent.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Entity not found")
    result = compile_entity_note(entity_id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Compile failed — no related documents, or LLM unavailable.",
        )
    _track_usage(request, "compile")
    return result


@router.get("/corpora/{corpus_id}/entities/{entity_id}")
async def api_get_entity(corpus_id: str, entity_id: str, request: Request):
    """Entity detail page: the entity + three buckets of related documents.

    See entities.get_entity_with_related_docs for the bucket semantics.
    """
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.entities import get_entity_with_related_docs
    ent = get_entity_with_related_docs(entity_id)
    if not ent or ent.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@router.post("/corpora/{corpus_id}/documents/{doc_id}/extract-entities")
async def api_extract_document_entities(corpus_id: str, doc_id: str, request: Request):
    """Run entity extraction on a single document."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "extract_entities")
    from noosphere.core.entities import enrich_document
    result = enrich_document(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    _track_usage(request, "extract_entities")
    return result


@router.post("/corpora/{corpus_id}/extract-entities")
async def api_extract_corpus_entities(
    corpus_id: str, req: ExtractEntitiesRequest, request: Request,
):
    """Batch entity extraction across unenriched documents.

    Separate from /enrich (which polls RSS feeds). This runs an LLM pass
    per doc to populate the entities table; call repeatedly until
    remaining == 0 on large corpora.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "extract_entities")
    from noosphere.core.entities import enrich_corpus
    result = enrich_corpus(corpus["id"], limit=max(1, min(req.limit, 200)))
    _track_usage(request, "extract_entities", tokens_used=result.get("enriched", 0))
    return result


@router.post("/corpora/{corpus_id}/compile")
async def api_compile_concept(corpus_id: str, req: CompileRequest, request: Request):
    """LLM-compile a concept note from retrieved passages (knowledge fusion)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import compile_concept_note

    try:
        result = compile_concept_note(corpus["id"], req.topic.strip(), top_k=req.top_k)
        _track_usage(request, "compile")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/documents/{doc_id}/recompile")
async def api_recompile_concept(
    corpus_id: str, doc_id: str, req: RecompileRequest, request: Request,
):
    """Regenerate a concept doc's compiled truth from its timeline sources.

    Snapshots the prior version to ``concept_versions`` so history is diff-able.
    Body ``{"force": true}`` bypasses the pending-changes threshold.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import recompile_concept_if_dirty

    try:
        result = recompile_concept_if_dirty(doc_id, force=req.force)
        if result.get("status") == "recompiled":
            _track_usage(request, "compile")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/documents/{doc_id}/refine-compile")
async def api_refine_concept(
    corpus_id: str, doc_id: str, req: RefineRequest, request: Request,
):
    """Apply a natural-language edit to a concept doc's compiled truth."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import refine_concept_note

    try:
        result = refine_concept_note(doc_id, req.instruction)
        _track_usage(request, "compile")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/corpora/{corpus_id}/entities/{entity_id}/refine-compile")
async def api_refine_entity(
    corpus_id: str, entity_id: str, req: RefineRequest, request: Request,
):
    """Apply a natural-language edit to an entity's compiled description."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.entities import refine_entity_note, get_entity

    ent = get_entity(entity_id)
    if not ent or ent.get("corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Entity not found")
    try:
        result = refine_entity_note(entity_id, req.instruction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(
            status_code=400,
            detail="Refine failed — LLM unavailable.",
        )
    _track_usage(request, "compile")
    return result


@router.get("/corpora/{corpus_id}/documents/{doc_id}/versions")
async def api_concept_versions(corpus_id: str, doc_id: str, request: Request):
    """List all snapshot versions of a concept doc (oldest first)."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.knowledge_growth import get_concept_versions

    return {"document_id": doc_id, "versions": get_concept_versions(doc_id)}


@router.post("/corpora/{corpus_id}/recompile-dirty")
async def api_recompile_dirty(
    corpus_id: str, req: RecompileDirtyRequest, request: Request,
):
    """Batch-recompile all dirty concept docs in this corpus."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "compile")
    from noosphere.core.knowledge_growth import recompile_dirty_concepts

    return recompile_dirty_concepts(corpus["id"], force=req.force)


@router.get("/corpora/{corpus_id}/knowledge-health")
async def api_knowledge_health(corpus_id: str, request: Request):
    """Corpus health / lint-style report (coverage, staleness, link hygiene)."""
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    from noosphere.core.knowledge_growth import corpus_knowledge_health

    try:
        return corpus_knowledge_health(corpus["id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/corpora/{corpus_id}/maintain")
async def api_maintain_corpus(corpus_id: str, req: MaintainRequest, request: Request):
    """Re-index corpus to repair search index drift (lightweight maintain pass)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import run_corpus_maintain

    try:
        return run_corpus_maintain(corpus["id"], force_reindex=req.force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/corpora/{corpus_id}/enrich")
async def api_enrich_corpus(corpus_id: str, request: Request):
    """Enrichment cycle: poll RSS feeds, re-index, and health check.

    Designed to be called periodically (cron, agent, or scheduler).
    Polls all known RSS feeds for new entries, re-indexes to pick up
    new content, and returns a health summary.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.knowledge_growth import (
        ingest_rss_feed, run_corpus_maintain, corpus_knowledge_health,
    )

    # 1. Discover feeds: find unique source_feed URLs from document metadata
    conn = get_conn()
    feed_rows = conn.execute(
        "SELECT DISTINCT json_extract(metadata_json, '$.source_feed') as feed "
        "FROM documents WHERE corpus_id=? AND json_extract(metadata_json, '$.source_feed') IS NOT NULL",
        (corpus["id"],),
    ).fetchall()
    feed_urls = [r["feed"] for r in feed_rows if r["feed"]]

    # 2. Poll each feed for new entries
    feed_results = []
    total_ingested = 0
    for url in feed_urls:
        try:
            result = ingest_rss_feed(corpus["id"], url, max_items=25)
            feed_results.append(result)
            total_ingested += result.get("ingested", 0)
        except Exception as e:
            feed_results.append({"feed_url": url, "error": str(e)})

    # 3. Re-index if new content was ingested
    index_result = {}
    if total_ingested > 0:
        try:
            index_result = run_corpus_maintain(corpus["id"], force_reindex=False)
        except Exception as e:
            index_result = {"error": str(e)}

    # 4. Health check
    try:
        health = corpus_knowledge_health(corpus["id"])
    except Exception as e:
        health = {"error": str(e)}

    return {
        "corpus_id": corpus["id"],
        "feeds_polled": len(feed_urls),
        "total_new_documents": total_ingested,
        "feed_results": feed_results,
        "index": index_result,
        "health": health,
    }


# ── Indexing ──

@router.post("/corpora/{corpus_id}/index")
async def api_index_corpus(corpus_id: str, request: Request, req: IndexRequest = None):
    """Run indexing (chunk + embed) over a corpus.

    Quota behavior: charged only when actual embedding work happens. The
    frontend fires /index after every ingest action via a debounced helper,
    so back-to-back ingests coalesce into one call; but even the one call
    returns `embedded=0` if content hashes unchanged (force=false). In that
    no-op case we skip quota deduction — the user shouldn't pay for a call
    that did no work. This keeps the "one user action ≠ N quota units" bug
    from reappearing as the UI evolves.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    # Peek at quota without deducting — actual deduction happens after we
    # know whether any work was done.
    _check_quota(request, "index")
    from noosphere.core.indexer import index_corpus
    kwargs = {}
    if req:
        if req.force:
            kwargs["force"] = True
        if req.chunk_strategy:
            kwargs["chunk_strategy"] = req.chunk_strategy
    try:
        result = index_corpus(corpus["id"], **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # Only charge when we actually re-embedded. A hash-matched no-op run
    # shouldn't burn a user's daily quota.
    if result.get("embedded", 0) > 0:
        _track_usage(request, "index")
    return result


# ── Search ──

@router.post("/corpora/{corpus_id}/search")
async def api_search(corpus_id: str, req: SearchRequest, request: Request):
    corpus = _resolve_corpus(corpus_id)
    token_id = _check_corpus_access(corpus, request)
    _check_quota(request, "search")
    agent_id = request.headers.get("x-agent-id", "")
    caller = "owner" if _is_owner_request(request) else "external"
    result = search_corpus(
        corpus["id"], req.query, top_k=req.top_k,
        include_context=req.include_context,
        detail=req.detail,
        agent_id=agent_id, token_id=token_id,
        caller=caller,
    )
    _track_usage(request, "search")
    return result


# ── KB-as-agent L0 interface (ask / describe / probe) ──

def _caller_corpus_id(request: Request) -> str:
    """Extract `X-Noosphere-Caller-Corpus` header. Returns the corpus id only if
    it resolves to a locally-known corpus — random IDs from external callers are
    ignored so citation graph can't be trivially poisoned. Later work: require
    the caller to authenticate as the corpus owner to strengthen this.
    """
    cid = (request.headers.get("x-noosphere-caller-corpus") or "").strip()
    if not cid:
        return ""
    c = get_corpus(cid) or get_corpus_by_slug(cid)
    return c["id"] if c else ""


@router.post("/corpora/{corpus_id}/ask")
async def api_ask(corpus_id: str, req: AskRequest, request: Request):
    """Synthesized answer with inline [N] citations, grounded in the corpus.

    Enforces access gating (public / private / token / paid) like search.

    If the caller sets `X-Noosphere-Caller-Corpus: {corpus_id}` and that corpus
    is locally known, a `query`-kind citation from caller to target is recorded
    (24h-deduped per pair) — this is how agent-to-agent usage accrues into
    `kb_reputation`.
    """
    corpus = _resolve_corpus(corpus_id)
    token_id = _check_corpus_access(corpus, request)
    _check_quota(request, "ask")
    agent_id = request.headers.get("x-agent-id", "")
    caller_corpus = _caller_corpus_id(request)
    caller = "owner" if _is_owner_request(request) else "external"
    try:
        result = kb_ask(
            corpus["id"], req.question, top_k=req.top_k,
            caller=caller, agent_id=agent_id, token_id=token_id,
        )
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    if result is None:
        raise HTTPException(status_code=404, detail="Corpus not found")
    if caller_corpus and caller_corpus != corpus["id"] and result.get("chunks_used", 0) > 0:
        _record_inter_kb_query(caller_corpus, corpus["id"], req.question[:200])
    _track_usage(request, "ask")
    return result


def _record_inter_kb_query(citing: str, cited: str, context: str = "") -> None:
    """Fire-and-forget wrapper around `record_inter_kb_query`. Silent on failure:
    attribution is best-effort, the query itself already succeeded."""
    try:
        from noosphere.core.citations import record_inter_kb_query
        record_inter_kb_query(citing, cited, context=context)
    except Exception as e:
        logger.warning(f"inter-KB citation record failed: {e}")


@router.get("/corpora/{corpus_id}/describe")
async def api_describe(corpus_id: str, request: Request):
    """Machine-readable capability card for a corpus.

    No authentication required — capability descriptions are discoverable
    so agents can evaluate relevance before committing to a query.
    """
    result = kb_describe(corpus_id) or kb_describe(
        (get_corpus_by_slug(corpus_id) or {}).get("id", "")
    )
    if not result:
        raise HTTPException(status_code=404, detail="Corpus not found")
    try:
        from noosphere.core.retrieval import log_query
        log_query(
            result["corpus_id"], "", 0, 0,
            agent_id=request.headers.get("x-agent-id", ""),
            action="describe",
        )
    except Exception:
        pass
    log_access(request, corpus_id=result["corpus_id"], surface="corpus_describe")
    return result


@router.post("/corpora/{corpus_id}/manifest/suggest")
async def api_manifest_suggest(corpus_id: str, request: Request):
    """Ask the LLM to propose capability-card fields from corpus content.

    Returns the proposal without applying it — owner may edit and apply via
    `PATCH /corpora/{id}`. Requires owner auth. Pro-tier quota in cloud mode.
    """
    from noosphere.core.manifest_autofill import suggest_manifest
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _check_quota(request, "manifest_suggest")
    try:
        proposal = suggest_manifest(corpus["id"])
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    if proposal is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot suggest manifest — corpus has no documents to infer from",
        )
    _track_usage(request, "manifest_suggest")
    return proposal


@router.post("/corpora/{corpus_id}/manifest/apply")
async def api_manifest_apply(corpus_id: str, req: ManifestApplyRequest, request: Request):
    """Apply a (possibly owner-edited) manifest proposal to the corpus.

    Only the fields present in the request body are updated. Equivalent to a
    targeted `PATCH` but scoped to the capability-card fields.
    """
    from noosphere.core.manifest_autofill import apply_proposal
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    proposal = {
        "task_types": req.task_types,
        "samples": req.samples,
        "description_suggestion": req.description_suggestion,
    }
    result = apply_proposal(corpus["id"], proposal, refresh_description=req.refresh_description)
    return result


@router.post("/corpora/{corpus_id}/route")
async def api_route(corpus_id: str, req: RouteRequest, request: Request):
    """Recommend other KBs that may better answer a question.

    Public — any agent can call. Returns a ranked list of candidate corpora
    (local + registered remote), excluding the source and any private corpora.
    Ranking combines keyword relevance + target KB reputation + explicit
    manifest endorsements from this corpus.
    """
    corpus = _resolve_corpus(corpus_id)
    if corpus.get("access_level") == "private":
        raise HTTPException(status_code=403, detail="Private corpus")
    result = kb_route(corpus["id"], req.question, limit=req.limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Corpus not found")
    return result


@router.get("/corpora/{corpus_id}/citations")
async def api_list_citations(corpus_id: str, direction: str = "out"):
    """List citations for a corpus. `direction=out` (default) returns what this
    KB cites; `direction=in` returns what cites this KB.
    """
    from noosphere.core.citations import citations_out as _out, citations_in as _in
    corpus = _resolve_corpus(corpus_id)
    if direction == "in":
        return {"citations": _in(corpus["id"]), "direction": "in"}
    return {"citations": _out(corpus["id"]), "direction": "out"}


@router.post("/corpora/{corpus_id}/citations")
async def api_record_citation(corpus_id: str, req: CitationRequest, request: Request):
    """Owner declares an explicit manifest citation — "this KB builds on KB X".

    Idempotent by (citing, cited, kind=manifest). Owner-only.
    """
    from noosphere.core.citations import upsert_manifest_citation, refresh_kb_reputation
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    if not req.cited_corpus_id or req.cited_corpus_id == corpus["id"]:
        raise HTTPException(status_code=400, detail="cited_corpus_id must be set and differ from source")
    result = upsert_manifest_citation(corpus["id"], req.cited_corpus_id, context=req.context)
    # Refresh the cited KB's reputation since it just received a new edge.
    try:
        refresh_kb_reputation(req.cited_corpus_id)
    except Exception:
        pass
    return result


@router.post("/corpora/{corpus_id}/preview-ask")
async def api_preview_ask(corpus_id: str, req: PreviewAskRequest, request: Request):
    """Low-cost evaluation query — bypasses access gating even for paid corpora.

    Returns a truncated synthesized answer so agents can assess KB fit before
    paying for full access. Rate-limited via the `preview_ask` quota action.
    """
    corpus = _resolve_corpus(corpus_id)
    if corpus.get("access_level") == "private":
        raise HTTPException(status_code=403, detail="Private corpus")
    _check_quota(request, "preview_ask")
    agent_id = request.headers.get("x-agent-id", "")
    try:
        result = kb_preview_ask(corpus["id"], req.question, agent_id=agent_id)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    if result is None:
        raise HTTPException(status_code=404, detail="Corpus not found")
    _track_usage(request, "preview_ask")
    log_access(request, corpus_id=corpus["id"], surface="corpus_preview_ask")
    return result


# ── Preview (discovery) ──

@router.get("/corpora/{corpus_id}/preview")
async def api_preview(corpus_id: str, request: Request):
    """Preview a knowledge base — returns sample chunks and quality signals.

    Available without authentication, even for paid corpora. Designed for
    agents evaluating whether a knowledge base is relevant before committing
    to a full query or purchase.
    """
    corpus = _resolve_corpus(corpus_id)
    log_access(request, corpus_id=corpus["id"], surface="corpus_preview")
    conn = get_conn()

    # Sample chunks: pick a few representative ones (newest, spread across documents)
    sample_chunks = conn.execute(
        """SELECT c.text, c.document_id, c.created_at,
                  d.title as document_title, d.doc_type
           FROM chunks c
           JOIN documents d ON d.id = c.document_id
           WHERE c.corpus_id=?
           ORDER BY c.created_at DESC
           LIMIT 20""",
        (corpus["id"],),
    ).fetchall()

    # Deduplicate by document — one chunk per document, max 5
    seen_docs = set()
    samples = []
    for row in sample_chunks:
        did = row["document_id"]
        if did in seen_docs:
            continue
        seen_docs.add(did)
        text = row["text"]
        # Truncate to ~200 chars for preview
        if len(text) > 250:
            text = text[:247] + "..."
        samples.append({
            "text": text,
            "document_title": row["document_title"],
            "document_type": row["doc_type"] or "",
        })
        if len(samples) >= 5:
            break

    # Quality signals
    query_count = conn.execute(
        "SELECT COUNT(*) as n FROM query_logs WHERE corpus_id=?",
        (corpus["id"],),
    ).fetchone()["n"]

    # Topic summary from tags + document types
    doc_types = conn.execute(
        "SELECT doc_type, COUNT(*) as cnt FROM documents WHERE corpus_id=? GROUP BY doc_type ORDER BY cnt DESC",
        (corpus["id"],),
    ).fetchall()

    tags = corpus.get("tags", [])
    if isinstance(tags, str):
        try:
            tags = _json.loads(tags)
        except Exception:
            tags = []

    return {
        "corpus_id": corpus["id"],
        "name": corpus["name"],
        "description": corpus.get("description", ""),
        "author": corpus.get("author_name", ""),
        "tags": tags,
        "access_level": corpus.get("access_level", "public"),
        "quality": {
            "document_count": corpus.get("document_count", 0),
            "chunk_count": corpus.get("chunk_count", 0),
            "word_count": corpus.get("word_count", 0),
            "query_count": query_count,
            "last_updated": corpus.get("updated_at", ""),
            "status": corpus.get("status", "draft"),
            "embedding_model": corpus.get("embedding_model", ""),
        },
        "capability": {
            "task_types": corpus.get("task_types", []),
            "autonomy_level": corpus.get("autonomy_level", 0),
            "source_composition": source_composition(corpus["id"]),
            "calibration_policy": corpus.get("calibration_policy"),
            "license_terms": corpus.get("license_terms"),
            "samples": corpus.get("samples", []),
            "kb_reputation": corpus.get("kb_reputation", 0.0) or 0.0,
        },
        "content_types": [{"type": r["doc_type"] or "doc", "count": r["cnt"]} for r in doc_types],
        "samples": samples,
    }


# ── Stats & Topics ──

@router.get("/corpora/{corpus_id}/stats")
async def api_stats(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    return {
        "corpus_id": corpus["id"], "name": corpus["name"],
        "document_count": corpus["document_count"],
        "chunk_count": corpus["chunk_count"],
        "word_count": corpus["word_count"],
        "embedding_model": corpus.get("embedding_model", ""),
        "status": corpus["status"],
        "access_level": corpus["access_level"],
        "updated_at": corpus["updated_at"],
    }


@router.get("/corpora/{corpus_id}/topics")
async def api_topics(corpus_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    docs = get_documents(corpus["id"])
    topics = set()
    for src in [corpus.get("tags", [])]:
        if isinstance(src, str):
            try: src = _json.loads(src)
            except Exception: src = []
        for t in (src if isinstance(src, list) else []):
            topics.add(t.strip().lower())
    for doc in docs:
        dt = doc.get("tags", "[]")
        if isinstance(dt, str):
            try: dt = _json.loads(dt)
            except Exception: dt = []
        for t in (dt if isinstance(dt, list) else []):
            topics.add(t.strip().lower())
    return {"topics": sorted(topics)}


# ── Export ──

@router.get("/corpora/{corpus_id}/export")
async def api_export_corpus(corpus_id: str, request: Request):
    """Export a corpus as a ZIP file."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.export import export_corpus
    from fastapi.responses import StreamingResponse
    buf = export_corpus(corpus["id"])
    slug = corpus.get("slug", corpus_id)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


# ── Access Tokens ──

@router.post("/corpora/{corpus_id}/tokens")
async def api_create_token(corpus_id: str, req: CreateTokenRequest, request: Request):
    """Create an access token for a corpus. Returns plaintext token (one-time)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import create_token
    return create_token(corpus["id"], label=req.label, permissions=req.permissions, expires_at=req.expires_at)


@router.get("/corpora/{corpus_id}/tokens")
async def api_list_tokens(corpus_id: str, request: Request):
    """List all access tokens for a corpus (without hashes)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import list_tokens
    return list_tokens(corpus["id"])


@router.delete("/corpora/{corpus_id}/tokens/{token_id}")
async def api_revoke_token(corpus_id: str, token_id: str, request: Request):
    """Revoke an access token."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.tokens import revoke_token
    if not revoke_token(token_id):
        raise HTTPException(status_code=404, detail="Token not found")
    return {"status": "revoked"}


# ── Query Logs / Analytics ──

@router.post("/search")
async def api_global_search(req: SearchRequest):
    """Search across ALL public corpora (local + registered remote nodes)."""
    corpora = list_corpora()
    ready = [c for c in corpora if c.get("status") == "ready" and c.get("access_level") == "public"]

    all_results = []
    for c in ready:
        try:
            # Cross-corpus search is always external w.r.t. each corpus.
            result = search_corpus(c["id"], req.query, top_k=req.top_k, include_context=req.include_context, caller="external")
            for r in result.get("results", []):
                r["corpus_id"] = c["id"]
                r["corpus_name"] = c["name"]
                r["source"] = "local"
                all_results.append(r)
        except Exception:
            logger.warning("Global search failed for corpus %s", c["id"], exc_info=True)
            continue

    remote_results = _search_registered_corpora(req.query, limit=req.top_k)
    all_results.extend(remote_results)

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "results": all_results[: req.top_k],
        "corpora_searched": len(ready) + len(remote_results),
    }


def _compute_quality_score(corpus: dict) -> float:
    """Compute a quality ranking score from objective signals (0.0–1.0).

    Combines Tier 2 signals (size, freshness, uptime) with Tier 3 `kb_reputation`
    (accumulated citation-weighted score). Tier 3 is capped at 0.35 so a brand
    new KB can still rank well via Tier 2 while an established KB gets a real
    lift from its reputation.
    """
    import math
    score = 0.0
    # Document count: log scale, max ~0.25 at 500+ docs
    doc_count = corpus.get("document_count", 0)
    if isinstance(doc_count, dict):
        doc_count = doc_count.get("document_count", 0)
    q = corpus.get("quality", {})
    if isinstance(q, dict):
        doc_count = doc_count or q.get("document_count", 0)
    score += min(0.25, math.log1p(doc_count) / 24)
    # Word count: log scale, max ~0.15 at 100k+ words
    word_count = q.get("word_count", 0) if isinstance(q, dict) else corpus.get("word_count", 0)
    score += min(0.15, math.log1p(word_count) / 80)
    # Health: online nodes get a bonus
    health = q.get("health_status", "") if isinstance(q, dict) else corpus.get("health_status", "")
    if health == "online":
        score += 0.1
    elif health == "degraded":
        score += 0.03
    # Access level: public gets slight preference (more useful for discovery)
    if corpus.get("access_level") == "public":
        score += 0.08
    elif corpus.get("access_level") == "paid":
        score += 0.04
    # Tier 3: KB reputation (accumulated citation signal)
    kbr = corpus.get("kb_reputation", 0.0) or 0.0
    if isinstance(kbr, dict):
        kbr = 0.0
    score += min(0.35, float(kbr))
    # Base score so nothing is zero
    score += 0.07
    return round(min(1.0, score), 4)


def _search_registered_corpora(query: str, limit: int = 20) -> list[dict]:
    """Search registered remote corpora by metadata (FTS or LIKE fallback)."""
    conn = get_conn()
    try:
        if is_pg():
            rows = conn.execute(
                """SELECT rc.*, rn.health_status
                   FROM registered_corpora rc
                   JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                   WHERE rn.health_status != 'offline'
                     AND rc.tsv @@ plainto_tsquery('english', ?)
                   ORDER BY ts_rank(rc.tsv, plainto_tsquery('english', ?)) DESC
                   LIMIT ?""",
                (query, query, limit),
            ).fetchall()
        else:
            fts_query = " OR ".join(f'"{w}"' for w in query.strip().split() if w)
            try:
                rows = conn.execute(
                    """SELECT rc.*, rn.health_status
                       FROM registered_corpora_fts fts
                       JOIN registered_corpora rc ON rc.id = fts.registry_id
                       JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                       WHERE registered_corpora_fts MATCH ?
                         AND rn.health_status != 'offline'
                       ORDER BY fts.rank LIMIT ?""",
                    (fts_query, limit),
                ).fetchall()
            except Exception:
                pattern = f"%{query.strip()}%"
                rows = conn.execute(
                    """SELECT rc.*, rn.health_status
                       FROM registered_corpora rc
                       JOIN registered_nodes rn ON rn.endpoint = rc.node_endpoint
                       WHERE (rc.name LIKE ? OR rc.description LIKE ? OR rc.author LIKE ?)
                         AND rn.health_status != 'offline'
                       ORDER BY rc.document_count DESC LIMIT ?""",
                    (pattern, pattern, pattern, limit),
                ).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        r = dict(row)
        tags = r.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = _json.loads(tags)
            except Exception:
                tags = []
        results.append({
            "corpus_id": r["corpus_id"],
            "corpus_name": r["name"],
            "description": r.get("description", ""),
            "author": r.get("author", ""),
            "tags": tags,
            "quality": {
                "document_count": r.get("document_count", 0),
                "chunk_count": r.get("chunk_count", 0),
                "word_count": r.get("word_count", 0),
                "last_updated": r.get("updated_at", ""),
                "health_status": r.get("health_status", "unknown"),
            },
            "access_level": r.get("access_level", "public"),
            "api_endpoint": f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}",
            "mcp_endpoint": f"{r['node_endpoint']}/mcp",
            "preview_url": f"{r['node_endpoint']}/api/v1/corpora/{r['corpus_id']}/preview",
            "source": "remote",
            "score": _compute_quality_score(r),
        })
    return results


# ── Chat ──

def _humanize_upstream_err(e: Exception, stage: str) -> str:
    """Extract the useful bit from an httpx error so users see the real cause
    (e.g. "User location is not supported" vs. a generic 5xx)."""
    import httpx
    if isinstance(e, httpx.HTTPStatusError):
        try:
            body = e.response.json()
            msg = body.get("error", {}).get("message") or body.get("error") or e.response.text[:200]
        except Exception:
            msg = e.response.text[:200]
        return f"{stage} failed ({e.response.status_code}): {msg}"
    return f"{stage} failed: {str(e)[:200]}"


@router.post("/chat")
async def api_global_chat(req: ChatRequest, request: Request):
    """Chat across all public corpora in the Noosphere."""
    import httpx
    _check_quota(request, "chat")
    from noosphere.core.chat import chat_with_noosphere
    try:
        result = chat_with_noosphere(req.message, history=req.history, top_k=req.top_k)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error — {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=_humanize_upstream_err(e, "Embedding"))
    _track_usage(request, "chat")
    return result


@router.post("/corpora/{corpus_id}/chat")
async def api_corpus_chat(corpus_id: str, req: ChatRequest, request: Request):
    """Chat with a specific corpus."""
    import uuid
    import httpx
    from datetime import datetime, timezone

    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    _check_quota(request, "chat")
    caller = "owner" if _is_owner_request(request) else "external"
    from noosphere.core.chat import chat_with_corpus
    try:
        result = chat_with_corpus(corpus["id"], req.message, history=req.history, top_k=req.top_k, caller=caller)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error — {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=_humanize_upstream_err(e, "Embedding"))

    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    session_id = req.session_id

    if not session_id:
        session_id = str(uuid.uuid4())
        title = req.message[:80]
        conn.execute(
            "INSERT INTO chat_sessions (id, corpus_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, corpus["id"], title, now, now),
        )
    else:
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, session_id))

    user_msg_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_msg_id, session_id, "user", req.message, now),
    )

    asst_msg_id = str(uuid.uuid4())
    citations_json = _json.dumps(result.get("citations")) if result.get("citations") else None
    conn.execute(
        "INSERT INTO chat_messages (id, session_id, role, content, citations_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (asst_msg_id, session_id, "assistant", result.get("response", ""), citations_json, now),
    )
    conn.commit()

    _track_usage(request, "chat")
    result["session_id"] = session_id
    return result


@router.get("/chat-sessions")
async def api_list_chat_sessions(request: Request, limit: int = 20):
    """List recent chat sessions, scoped to the active workspace.

    Org workspace → only sessions whose parent corpus belongs to that org.
    Personal workspace → only sessions whose parent corpus is personal
    (org_id IS NULL) — keeps a member's personal scratchpads out of the
    org sidebar and vice versa.
    """
    conn = get_conn()
    kind, active_org = _active_workspace(request)
    base = (
        "SELECT s.id, s.corpus_id, s.title, s.created_at, s.updated_at, "
        "       c.name as corpus_name, "
        "       (SELECT COUNT(*) FROM chat_messages WHERE session_id=s.id) as message_count "
        "FROM chat_sessions s LEFT JOIN corpora c ON c.id = s.corpus_id "
    )
    if kind == "org" and active_org:
        rows = conn.execute(
            base + "WHERE c.org_id = ? ORDER BY s.updated_at DESC LIMIT ?",
            (active_org, limit),
        ).fetchall()
    else:
        user_id = _get_user_id(request)
        if _is_cloud() and user_id:
            rows = conn.execute(
                base + "WHERE c.org_id IS NULL AND c.owner_id = ? ORDER BY s.updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                base + "WHERE c.org_id IS NULL ORDER BY s.updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.get("/chat-sessions/{session_id}")
async def api_get_chat_session(session_id: str, request: Request, limit: int = 500, offset: int = 0):
    """Get a chat session with its messages, paginated.

    ``limit`` is capped at 1000 to keep a single response bounded — sessions
    longer than that are rare today, but unbounded reads of the messages
    table would slow the UI noticeably and were a real risk on long-lived
    chats. Citation titles are re-resolved against the current document
    rows so renames/deletes stop showing stale labels in past replies.
    """
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    conn = get_conn()
    session = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    corpus = _resolve_corpus(session["corpus_id"])
    _check_corpus_access(corpus, request)
    total = conn.execute(
        "SELECT COUNT(*) AS n FROM chat_messages WHERE session_id=?",
        (session_id,),
    ).fetchone()["n"]
    messages = conn.execute(
        "SELECT id, role, content, citations_json, lines_json, created_at FROM chat_messages "
        "WHERE session_id=? ORDER BY created_at ASC LIMIT ? OFFSET ?",
        (session_id, limit, offset),
    ).fetchall()
    result = dict(session)
    result["message_count"] = total
    result["messages"] = []
    for m in messages:
        msg = dict(m)
        if msg.get("citations_json"):
            cites = _json.loads(msg["citations_json"])
            # Resolve titles fresh: a doc renamed since the chat happened
            # would otherwise display its stale title forever. A deleted
            # doc gets a clear "[deleted]" marker rather than a dangling
            # stale name pointing nowhere.
            if isinstance(cites, list):
                doc_ids = [c.get("document_id") for c in cites if isinstance(c, dict) and c.get("document_id")]
                if doc_ids:
                    placeholders = ",".join("?" for _ in doc_ids)
                    rows = conn.execute(
                        f"SELECT id, title FROM documents WHERE id IN ({placeholders})",
                        doc_ids,
                    ).fetchall()
                    title_by_id = {r["id"]: r["title"] for r in rows}
                    for c in cites:
                        if not isinstance(c, dict):
                            continue
                        did = c.get("document_id")
                        if did and did in title_by_id:
                            c["document_title"] = title_by_id[did]
                        elif did:
                            c["document_title"] = "[deleted source]"
                            c["deleted"] = True
            msg["citations"] = cites
        msg.pop("citations_json", None)
        # Parse the structured /terminal payload so the client can replay
        # the original turn (separate bubbles + cards) instead of rendering
        # the flattened content as one merged block. Pre-migration rows
        # have lines_json=NULL and the client falls back to content.
        if msg.get("lines_json"):
            try:
                msg["lines"] = _json.loads(msg["lines_json"])
            except Exception:
                msg["lines"] = None
        msg.pop("lines_json", None)
        result["messages"].append(msg)
    return result


@router.delete("/chat-sessions/{session_id}")
async def api_delete_chat_session(session_id: str, request: Request):
    """Delete a chat session and all its messages."""
    conn = get_conn()
    session = conn.execute("SELECT * FROM chat_sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    corpus = _resolve_corpus(session["corpus_id"])
    _require_owner(request, corpus)
    conn.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    conn.commit()
    return {"ok": True}


@router.get("/corpora/{corpus_id}/analytics")
async def api_analytics(corpus_id: str, request: Request, limit: int = 50):
    corpus = _resolve_corpus(corpus_id)
    _check_corpus_access(corpus, request)
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM query_logs WHERE corpus_id=? ORDER BY created_at DESC LIMIT ?",
        (corpus["id"], limit),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM query_logs WHERE corpus_id=?",
        (corpus["id"],),
    ).fetchone()
    return {
        "total_queries": total["cnt"],
        "recent_queries": [dict(r) for r in rows],
    }


@router.get("/corpora/{corpus_id}/insights")
async def api_insights(corpus_id: str, request: Request, window: str = "7d"):
    """Aggregated agent-activity metrics for the corpus Insights tab.

    Counters break down query_logs by action (describe / preview_ask / ask),
    and conversion is the share of previewers who went on to a full `ask`.
    `top_citing` surfaces which other KBs link to this one in the citation
    graph — incoming edges from `corpus_citations`.
    """
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)

    # Window → cutoff. Default 7 days; 30d supported. Anything else → all-time.
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    if window == "30d":
        since = (now - timedelta(days=30)).isoformat()
    elif window == "all":
        since = "1970-01-01T00:00:00+00:00"
    else:
        window = "7d"
        since = (now - timedelta(days=7)).isoformat()

    conn = get_conn()

    # Counters by action. COALESCE handles pre-migration rows (NULL action).
    rows = conn.execute(
        """SELECT COALESCE(action, 'ask') as action, COUNT(*) as n
           FROM query_logs
           WHERE corpus_id=? AND created_at >= ?
           GROUP BY COALESCE(action, 'ask')""",
        (corpus["id"], since),
    ).fetchall()
    counters = {"describe": 0, "preview_ask": 0, "ask": 0}
    for r in rows:
        counters[r["action"]] = r["n"]

    # Unique callers (by agent_id) — rough "how many distinct agents" signal.
    unique_callers_row = conn.execute(
        """SELECT COUNT(DISTINCT agent_id) as n
           FROM query_logs
           WHERE corpus_id=? AND created_at >= ? AND agent_id != ''""",
        (corpus["id"], since),
    ).fetchone()
    unique_callers = unique_callers_row["n"] if unique_callers_row else 0

    # preview_ask → ask conversion. Defined only when preview_ask > 0.
    conversion = None
    if counters["preview_ask"] > 0:
        conversion = round(counters["ask"] / counters["preview_ask"], 3)

    # Top citing KBs — incoming edges from corpus_citations, joined to local
    # corpora for display names. Remote citings keep their raw id.
    top_citing_rows = conn.execute(
        """SELECT citing_corpus_id, COUNT(*) as n
           FROM corpus_citations
           WHERE cited_corpus_id=? AND created_at >= ?
           GROUP BY citing_corpus_id
           ORDER BY n DESC
           LIMIT 10""",
        (corpus["id"], since),
    ).fetchall()
    top_citing = []
    for r in top_citing_rows:
        cid = r["citing_corpus_id"]
        name_row = conn.execute(
            "SELECT name, slug FROM corpora WHERE id=?", (cid,),
        ).fetchone()
        top_citing.append({
            "corpus_id": cid,
            "name": name_row["name"] if name_row else cid,
            "slug": name_row["slug"] if name_row else "",
            "count": r["n"],
            "local": bool(name_row),
        })

    # Revenue (cloud paid corpora only) — paid queries and total amount.
    revenue = None
    try:
        rev_row = conn.execute(
            """SELECT COUNT(*) as n, COALESCE(SUM(amount_cents), 0) as cents
               FROM payments
               WHERE corpus_id=? AND status='completed' AND created_at >= ?""",
            (corpus["id"], since),
        ).fetchone()
        if rev_row:
            revenue = {
                "paid_queries": rev_row["n"],
                "total_cents": rev_row["cents"],
            }
    except Exception:
        pass

    # Discovery Reach + Revenue Health — separate axes from the network-
    # internal trust signal (KBR) and the funnel counters above. Reach
    # captures external/anonymous AI traffic (Perplexity, Claude search,
    # ChatGPT browse, generic crawlers) that query_logs deliberately
    # ignores; Revenue Health is the lagging commercial artifact.
    from noosphere.core.access_log import discovery_reach, revenue_health as _rev_health
    try:
        reach = discovery_reach(corpus["id"], window=window)
    except Exception:
        reach = None
    try:
        rev_health = _rev_health(corpus["id"], window=("30d" if window != "all" else "all"))
    except Exception:
        rev_health = None

    return {
        "corpus_id": corpus["id"],
        "window": window,
        "counters": counters,
        "unique_callers": unique_callers,
        "conversion": conversion,
        "top_citing": top_citing,
        "revenue": revenue,
        "discovery_reach": reach,
        "revenue_health": rev_health,
    }


# ── Network Discovery (built-in registry) ──


class RegisterNodeRequest(BaseModel):
    node_version: str = ""
    endpoint: str
    corpora: list[dict]


class DeregisterNodeRequest(BaseModel):
    endpoint: str


def _rebuild_rc_fts(conn, node_endpoint: str):
    """Rebuild FTS entries for all registered corpora belonging to a node."""
    if is_pg():
        conn.execute(
            """UPDATE registered_corpora
               SET tsv = to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,'') || ' ' || coalesce(author,''))
               WHERE node_endpoint=?""",
            (node_endpoint,),
        )
    else:
        conn.execute(
            "DELETE FROM registered_corpora_fts WHERE registry_id IN "
            "(SELECT id FROM registered_corpora WHERE node_endpoint=?)",
            (node_endpoint,),
        )
        rows = conn.execute(
            "SELECT id, name, description, author, tags FROM registered_corpora WHERE node_endpoint=?",
            (node_endpoint,),
        ).fetchall()
        for row in rows:
            conn.execute(
                "INSERT INTO registered_corpora_fts(name, description, author, tags, registry_id) VALUES (?, ?, ?, ?, ?)",
                (row["name"], row["description"] or "", row["author"] or "", row["tags"] or "", row["id"]),
            )


@router.post("/register")
async def api_register_node(req: RegisterNodeRequest):
    """Register a self-hosted node and its corpora for network discovery."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    endpoint = req.endpoint.rstrip("/")

    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")
    if not req.corpora:
        raise HTTPException(status_code=400, detail="at least one corpus is required")

    existing = conn.execute("SELECT endpoint FROM registered_nodes WHERE endpoint=?", (endpoint,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE registered_nodes SET node_version=?, last_seen_at=?, health_status='online', consecutive_failures=0 WHERE endpoint=?",
            (req.node_version, now, endpoint),
        )
    else:
        conn.execute(
            "INSERT INTO registered_nodes (endpoint, node_version, first_seen_at, last_seen_at, health_status) VALUES (?, ?, ?, ?, 'online')",
            (endpoint, req.node_version, now, now),
        )

    registered = 0
    for c in req.corpora:
        row_id = f"{endpoint}:{c.get('corpus_id', '')}"
        tags_json = _json.dumps(c.get("tags", [])) if isinstance(c.get("tags"), list) else c.get("tags", "[]")
        task_types_json = _json.dumps(c.get("task_types", [])) if isinstance(c.get("task_types"), list) else c.get("task_types", "[]")
        source_comp_json = _json.dumps(c.get("source_composition", {})) if isinstance(c.get("source_composition"), dict) else c.get("source_composition", "{}")
        autonomy_level = int(c.get("autonomy_level", 0) or 0)
        kb_reputation = float(c.get("kb_reputation", 0.0) or 0.0)
        corpus_id = c.get("corpus_id", "")

        existing_corpus = conn.execute(
            "SELECT id FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?",
            (endpoint, corpus_id),
        ).fetchone()

        if existing_corpus:
            conn.execute(
                """UPDATE registered_corpora SET name=?, slug=?, description=?, author=?,
                   tags=?, document_count=?, chunk_count=?, word_count=?,
                   access_level=?, status=?, task_types=?, autonomy_level=?,
                   source_composition=?, kb_reputation=?, updated_at=?
                   WHERE node_endpoint=? AND corpus_id=?""",
                (c.get("name", ""), c.get("slug", ""), c.get("description", ""), c.get("author", ""),
                 tags_json, c.get("document_count", 0), c.get("chunk_count", 0), c.get("word_count", 0),
                 c.get("access_level", "public"), c.get("status", "draft"),
                 task_types_json, autonomy_level, source_comp_json, kb_reputation,
                 now, endpoint, corpus_id),
            )
        else:
            conn.execute(
                """INSERT INTO registered_corpora
                   (id, node_endpoint, corpus_id, name, slug, description, author,
                    tags, document_count, chunk_count, word_count, access_level, status,
                    task_types, autonomy_level, source_composition, kb_reputation,
                    registered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row_id, endpoint, corpus_id, c.get("name", ""), c.get("slug", ""),
                 c.get("description", ""), c.get("author", ""), tags_json,
                 c.get("document_count", 0), c.get("chunk_count", 0), c.get("word_count", 0),
                 c.get("access_level", "public"), c.get("status", "draft"),
                 task_types_json, autonomy_level, source_comp_json, kb_reputation,
                 now, now),
            )
        registered += 1

    registered_ids = {c.get("corpus_id", "") for c in req.corpora}
    old_rows = conn.execute(
        "SELECT corpus_id FROM registered_corpora WHERE node_endpoint=?", (endpoint,)
    ).fetchall()
    for row in old_rows:
        if row["corpus_id"] not in registered_ids:
            if not is_pg():
                conn.execute(
                    "DELETE FROM registered_corpora_fts WHERE registry_id IN "
                    "(SELECT id FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?)",
                    (endpoint, row["corpus_id"]),
                )
            conn.execute(
                "DELETE FROM registered_corpora WHERE node_endpoint=? AND corpus_id=?",
                (endpoint, row["corpus_id"]),
            )

    _rebuild_rc_fts(conn, endpoint)
    conn.commit()
    return {"status": "ok", "registered": registered, "endpoint": endpoint}


@router.post("/deregister")
async def api_deregister_node(req: DeregisterNodeRequest):
    """Remove a self-hosted node and all its corpora from the network."""
    conn = get_conn()
    endpoint = req.endpoint.rstrip("/")

    if not is_pg():
        conn.execute(
            "DELETE FROM registered_corpora_fts WHERE registry_id IN "
            "(SELECT id FROM registered_corpora WHERE node_endpoint=?)",
            (endpoint,),
        )
    conn.execute("DELETE FROM registered_corpora WHERE node_endpoint=?", (endpoint,))
    conn.execute("DELETE FROM registered_nodes WHERE endpoint=?", (endpoint,))
    conn.commit()
    return {"status": "ok"}


@router.get("/network/search")
async def api_network_search(
    q: str = Query(..., description="Search query"),
    access_level: str = Query("", description="Filter by access level"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search the entire Noosphere network — local corpora + registered remote nodes."""
    if len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    results = _search_registered_corpora(q, limit=limit)

    local_corpora = list_corpora()
    for c in local_corpora:
        if c.get("access_level") == "private":
            continue
        name = c.get("name", "")
        desc = c.get("description", "")
        q_lower = q.lower()
        if q_lower in name.lower() or q_lower in desc.lower() or any(q_lower in t.lower() for t in (c.get("tags") or [])):
            tags = c.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = _json.loads(tags)
                except Exception:
                    tags = []
            results.append({
                "corpus_id": c["id"],
                "corpus_name": name,
                "description": desc,
                "author": c.get("author_name", ""),
                "tags": tags,
                "document_count": c.get("document_count", 0),
                "access_level": c.get("access_level", "public"),
                "source": "local",
                "score": 1.0,
            })

    # Compute quality scores for local results too
    for r in results:
        if r.get("source") == "local":
            r["score"] = _compute_quality_score(r)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "query": q,
        "results": results[offset : offset + limit],
        "count": len(results[offset : offset + limit]),
        "total": len(results),
    }


@router.get("/network/nodes")
async def api_network_nodes():
    """List all registered self-hosted nodes."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT rn.*, COUNT(rc.id) as corpus_count,
                      COALESCE(SUM(rc.document_count), 0) as total_documents,
                      COALESCE(SUM(rc.word_count), 0) as total_words
               FROM registered_nodes rn
               LEFT JOIN registered_corpora rc ON rc.node_endpoint = rn.endpoint
               GROUP BY rn.endpoint
               ORDER BY rn.last_seen_at DESC"""
        ).fetchall()
    except Exception:
        rows = []
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}


# ── Peer subscriptions (L3 Networked) ──

@router.post("/corpora/{corpus_id}/subscriptions")
async def api_create_peer_subscription(
    corpus_id: str, req: CreatePeerSubscriptionRequest, request: Request,
):
    """Create a peer subscription — owner-only on the subscriber corpus."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)

    from noosphere.core.peer_subscriptions import create_subscription

    # Resolve target_corpus_id: accept either a UUID or a slug (UI sends slug).
    target_id = req.target_corpus_id
    if target_id:
        tc = get_corpus(target_id) or get_corpus_by_slug(target_id)
        target_id = tc["id"] if tc else target_id

    approved_by = _get_user_id(request) or "owner"
    try:
        sub = create_subscription(
            corpus["id"], mode=req.mode,
            target_corpus_id=target_id, target_endpoint=req.target_endpoint,
            target_slug=req.target_slug,
            query=req.query, topic_filter=req.topic_filter,
            cadence_minutes=req.cadence_minutes,
            max_docs_per_cycle=req.max_docs_per_cycle,
            bearer_token=req.bearer_token, auth_mode=req.auth_mode,
            budget_cents_per_month=req.budget_cents_per_month,
            approved_by=approved_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sub


@router.get("/corpora/{corpus_id}/subscriptions")
async def api_list_peer_subscriptions(corpus_id: str, request: Request):
    """List subscriptions for a corpus. Owner-only — exposes outbound intent."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.peer_subscriptions import list_subscriptions
    return {"subscriptions": list_subscriptions(corpus["id"])}


@router.patch("/corpora/{corpus_id}/subscriptions/{sub_id}")
async def api_patch_peer_subscription(
    corpus_id: str, sub_id: str, req: UpdatePeerSubscriptionRequest, request: Request,
):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.peer_subscriptions import (
        get_subscription, pause_subscription, resume_subscription, update_subscription,
    )
    sub = get_subscription(sub_id)
    if not sub or sub.get("subscriber_corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if req.status == "paused":
        pause_subscription(sub_id)
    elif req.status == "active":
        resume_subscription(sub_id)

    kwargs = {
        k: v for k, v in {
            "cadence_minutes": req.cadence_minutes,
            "query": req.query,
            "topic_filter": req.topic_filter,
            "max_docs_per_cycle": req.max_docs_per_cycle,
            "budget_cents_per_month": req.budget_cents_per_month,
        }.items() if v is not None
    }
    if kwargs:
        update_subscription(sub_id, **kwargs)
    return get_subscription(sub_id)


@router.delete("/corpora/{corpus_id}/subscriptions/{sub_id}")
async def api_delete_peer_subscription(corpus_id: str, sub_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.peer_subscriptions import get_subscription, revoke_subscription
    sub = get_subscription(sub_id)
    if not sub or sub.get("subscriber_corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    revoke_subscription(sub_id)
    return {"status": "revoked"}


@router.get("/corpora/{corpus_id}/subscriptions/{sub_id}/runs")
async def api_peer_subscription_runs(corpus_id: str, sub_id: str, request: Request):
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.peer_subscriptions import get_subscription, list_runs
    sub = get_subscription(sub_id)
    if not sub or sub.get("subscriber_corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"runs": list_runs(sub_id)}


@router.post("/corpora/{corpus_id}/subscriptions/{sub_id}/run")
async def api_run_peer_subscription_now(corpus_id: str, sub_id: str, request: Request):
    """Manual run trigger — useful for testing a new subscription without
    waiting for the cron tick. Owner-only."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.peer_subscriptions import get_subscription
    from noosphere.core.peer_runner import run_subscription
    sub = get_subscription(sub_id)
    if not sub or sub.get("subscriber_corpus_id") != corpus["id"]:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return run_subscription(sub_id)


@router.post("/cron/run-peer-subscriptions")
async def api_cron_run_peer_subscriptions(limit: int = 20):
    """Scheduler tick — execute up to `limit` due subscriptions.

    Safe to call every few minutes; internal picker only returns active subs
    whose next_run_at has passed. No auth required (cron endpoint).
    """
    from noosphere.core.peer_runner import run_due_subscriptions
    results = run_due_subscriptions(limit=limit)
    return {"status": "ok", "ran": len(results), "results": results}


@router.post("/cron/refresh-kb-reputation")
async def api_cron_refresh_kbr():
    """Batch-refresh `kb_reputation` for every local corpus.

    KBR v2 signals (retention, satisfaction) change continuously with traffic,
    so a nightly cron keeps rankings current. Citation-triggered refreshes
    (from `record_inter_kb_query` and manifest citations) cover point-in-time
    updates; this fills the rolling-window gap.
    """
    from noosphere.core.citations import refresh_all_kb_reputations
    n = refresh_all_kb_reputations()
    return {"status": "ok", "refreshed": n}


@router.get("/cron/health-check")
async def api_cron_health_check(request: Request):
    """Cron-compatible endpoint: ping all registered nodes and update health status.

    Replaces the old daemon thread. Call via Vercel Cron, external cron,
    or manually. Safe to call frequently — each check is a quick HTTP GET.
    """
    import httpx

    conn = get_conn()
    try:
        nodes = conn.execute("SELECT endpoint FROM registered_nodes").fetchall()
    except Exception:
        return {"status": "ok", "checked": 0}

    now = datetime.now(timezone.utc).isoformat()
    checked = 0
    for node in nodes:
        endpoint = node["endpoint"]
        try:
            resp = httpx.get(f"{endpoint}/api/v1/health", timeout=10, follow_redirects=True)
            if resp.status_code == 200:
                conn.execute(
                    "UPDATE registered_nodes SET health_status='online', last_health_at=?, consecutive_failures=0 WHERE endpoint=?",
                    (now, endpoint),
                )
                conn.commit()
                checked += 1
                continue
        except Exception:
            pass
        row = conn.execute("SELECT consecutive_failures FROM registered_nodes WHERE endpoint=?", (endpoint,)).fetchone()
        if not row:
            continue
        failures = (row["consecutive_failures"] or 0) + 1
        status = "offline" if failures >= 3 else "degraded"
        conn.execute(
            "UPDATE registered_nodes SET health_status=?, last_health_at=?, consecutive_failures=? WHERE endpoint=?",
            (status, now, failures, endpoint),
        )
        conn.commit()
        checked += 1

    return {"status": "ok", "checked": checked}


@router.get("/network/stats")
async def api_network_stats():
    """Network-wide statistics (local + remote)."""
    conn = get_conn()
    local_corpora = list_corpora()
    local_public = [c for c in local_corpora if c.get("access_level") != "private"]

    try:
        nodes_total = conn.execute("SELECT COUNT(*) as n FROM registered_nodes").fetchone()["n"]
        nodes_online = conn.execute("SELECT COUNT(*) as n FROM registered_nodes WHERE health_status='online'").fetchone()["n"]
        remote_corpora = conn.execute("SELECT COUNT(*) as n FROM registered_corpora").fetchone()["n"]
        remote_docs = conn.execute("SELECT COALESCE(SUM(document_count), 0) as n FROM registered_corpora").fetchone()["n"]
        remote_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) as n FROM registered_corpora").fetchone()["n"]
    except Exception:
        nodes_total = nodes_online = remote_corpora = remote_docs = remote_words = 0

    local_docs = sum(c.get("document_count", 0) for c in local_public)
    local_words = sum(c.get("word_count", 0) for c in local_public)

    return {
        "nodes_total": nodes_total + 1,
        "nodes_online": nodes_online + 1,
        "corpora_total": len(local_public) + remote_corpora,
        "total_documents": local_docs + remote_docs,
        "total_words": local_words + remote_words,
        "local_corpora": len(local_public),
        "remote_corpora": remote_corpora,
        "version": __version__,
    }


# ── Payments (Stripe) ──


class CheckoutRequest(BaseModel):
    success_url: str = ""
    cancel_url: str = ""
    payer_email: str = ""
    agent_id: str = ""


class PricingRequest(BaseModel):
    """Set pricing for a paid corpus."""
    type: str = "per_query"  # "per_query" or "subscription"
    amount_cents: int = 500
    currency: str = "usd"
    queries_per_payment: int = 100  # per_query only
    stripe_price_id: str = ""       # subscription only


@router.post("/corpora/{corpus_id}/checkout")
async def api_checkout(corpus_id: str, req: CheckoutRequest, request: Request):
    """Create a Stripe Checkout session for a paid corpus."""
    corpus = _resolve_corpus(corpus_id)
    if corpus.get("access_level") != "paid":
        raise HTTPException(status_code=400, detail="This corpus is not set to paid access")

    from noosphere.core.payments import create_checkout_session, PaymentError
    try:
        return create_checkout_session(
            corpus,
            success_url=req.success_url,
            cancel_url=req.cancel_url,
            payer_email=req.payer_email,
            agent_id=req.agent_id,
        )
    except PaymentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


class SettleRequest(BaseModel):
    """Body for POST /corpora/{id}/settle.

    Either provide `payment_proof` directly (e.g. the agent's MCP client
    can't easily set arbitrary HTTP headers), or send the proof via the
    `X-PAYMENT` header and leave the body empty. `mint_access_token` mints
    a short-lived bearer token usable for subsequent calls — useful for
    batched workflows that don't want to re-pay each call.
    """

    payment_proof: str = ""
    mint_access_token: bool = True


@router.post("/corpora/{corpus_id}/settle")
async def api_settle(corpus_id: str, req: SettleRequest, request: Request):
    """Verify an x402 payment proof and grant access to a paid corpus.

    Used by agents that hit 402 on a paid endpoint and want to satisfy the
    challenge before retrying. Returns the verified settlement plus —
    optionally — a freshly-minted access token they can present as
    `Authorization: Bearer <token>` on subsequent calls within the TTL.
    Per-call x402 retries with `X-PAYMENT` are also fully supported on the
    original endpoint and don't require a token.
    """
    corpus = _resolve_corpus(corpus_id)
    if corpus.get("access_level") != "paid":
        raise HTTPException(
            status_code=400, detail="This corpus is not set to paid access"
        )
    proof = req.payment_proof or (request.headers.get("x-payment") or "").strip()
    if not proof:
        raise HTTPException(
            status_code=400,
            detail="Provide payment_proof in body or X-PAYMENT header",
        )
    agent_id = request.headers.get("x-agent-id", "")
    resource = f"/api/v1/corpora/{corpus['id']}/search"
    result, settlement_id = verify_facilitator_proof(
        corpus, proof, resource=resource, agent_id=agent_id
    )
    if not result.valid:
        raise HTTPException(status_code=402, detail=result.reason or "Payment invalid")

    response: dict = {
        "settlement_id": settlement_id,
        "amount_cents": result.amount_cents,
        "scheme": result.scheme,
        "network": result.network,
        "settlement_tx": result.settlement_tx,
        "payer_id": result.payer_id,
    }
    if req.mint_access_token:
        from noosphere.core.agent_payments import mint_access_token, ACCESS_TOKEN_TTL_SECONDS

        _, raw = mint_access_token(corpus["id"])
        response["access_token"] = raw
        response["access_token_ttl_seconds"] = ACCESS_TOKEN_TTL_SECONDS
    return response


@router.post("/corpora/{corpus_id}/pricing")
async def api_set_pricing(corpus_id: str, req: PricingRequest, request: Request):
    """Set pricing config for a corpus. Also sets access_level to 'paid'."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    _require_originals_for_public_access(corpus["id"], "paid")

    import json as _j
    pricing = {
        "type": req.type,
        "amount_cents": req.amount_cents,
        "currency": req.currency,
    }
    if req.type == "per_query":
        pricing["queries_per_payment"] = req.queries_per_payment
    elif req.type == "subscription":
        if not req.stripe_price_id:
            raise HTTPException(status_code=400, detail="subscription type requires stripe_price_id")
        pricing["stripe_price_id"] = req.stripe_price_id

    from noosphere.core.corpus import update_corpus
    result = update_corpus(corpus["id"], pricing_json=_j.dumps(pricing), access_level="paid")
    return {"pricing": pricing, "corpus": result}


@router.get("/corpora/{corpus_id}/pricing")
async def api_get_pricing(corpus_id: str, request: Request):
    """Get pricing config for a corpus."""
    corpus = _resolve_corpus(corpus_id)
    from noosphere.core.payments import get_pricing
    pricing = get_pricing(corpus)
    return {"pricing": pricing, "access_level": corpus.get("access_level", "public")}


@router.get("/corpora/{corpus_id}/revenue")
async def api_revenue(corpus_id: str, request: Request):
    """Revenue dashboard for a paid corpus (owner only)."""
    corpus = _resolve_corpus(corpus_id)
    _require_owner(request, corpus)
    from noosphere.core.payments import get_revenue_stats
    return get_revenue_stats(corpus_id)


@router.post("/stripe/webhook")
async def api_stripe_webhook(request: Request):
    """Handle Stripe webhook events (payment completion, refunds, subscription cancellation)."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    from noosphere.core.payments import handle_webhook_event, PaymentError
    try:
        result = handle_webhook_event(payload, sig)
        return result
    except PaymentError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ── Team workspaces (orgs, members, invites, audit) ────────────────


class CreateOrgRequest(BaseModel):
    name: str
    slug: str = ""


class UpdateOrgRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    settings: Optional[dict] = None


class CreateInviteRequest(BaseModel):
    role: str = orgs_mod.ROLE_EDITOR
    ttl_days: int = 14


class UpdateMemberRoleRequest(BaseModel):
    role: str


def _require_user(request: Request) -> str:
    """Require an identified user; 401 otherwise. Used for org write paths."""
    uid = _get_user_id(request)
    if not uid:
        raise HTTPException(status_code=401, detail="User identity required")
    return uid


def _require_org_member(request: Request, org_id: str) -> tuple[str, str]:
    """Require the caller to be a member of the org. Returns (user_id, role)."""
    uid = _require_user(request)
    role = orgs_mod.member_role(org_id, uid)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    return uid, role


def _require_org_role(request: Request, org_id: str, min_role: str) -> tuple[str, str]:
    uid, role = _require_org_member(request, org_id)
    if not orgs_mod.role_at_least(role, min_role):
        raise HTTPException(status_code=403, detail=f"Requires {min_role} or higher")
    return uid, role


def _resolve_org(org_id: str) -> dict:
    org = orgs_mod.get_org(org_id) or orgs_mod.get_org_by_slug(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/orgs")
async def api_list_orgs(request: Request):
    uid = _get_user_id(request)
    if not uid:
        return []
    return orgs_mod.list_orgs_for_user(uid)


@router.post("/orgs")
async def api_create_org(req: CreateOrgRequest, request: Request):
    uid = _require_user(request)
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name required")
    try:
        org = orgs_mod.create_org(req.name.strip(), owner_user_id=uid, slug=req.slug)
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    orgs_mod.log_audit(
        "org.create", org_id=org["id"], actor_user_id=uid,
        resource_type="org", resource_id=org["id"],
        metadata={"name": org["name"], "slug": org["slug"]},
        ip_addr=_client_ip(request),
    )
    return org


@router.get("/orgs/{org_id}")
async def api_get_org(org_id: str, request: Request):
    org = _resolve_org(org_id)
    _require_org_member(request, org["id"])
    return org


@router.patch("/orgs/{org_id}")
async def api_update_org(org_id: str, req: UpdateOrgRequest, request: Request):
    org = _resolve_org(org_id)
    uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        result = orgs_mod.update_org(org["id"], **updates)
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    orgs_mod.log_audit(
        "org.update", org_id=org["id"], actor_user_id=uid,
        resource_type="org", resource_id=org["id"],
        metadata={"fields": list(updates.keys())},
        ip_addr=_client_ip(request),
    )
    return result


@router.delete("/orgs/{org_id}")
async def api_delete_org(org_id: str, request: Request):
    org = _resolve_org(org_id)
    uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_OWNER)
    ok = orgs_mod.delete_org(org["id"])
    orgs_mod.log_audit(
        "org.delete", org_id=org["id"], actor_user_id=uid,
        resource_type="org", resource_id=org["id"],
        ip_addr=_client_ip(request),
    )
    return {"deleted": ok}


@router.get("/orgs/{org_id}/members")
async def api_list_members(org_id: str, request: Request):
    org = _resolve_org(org_id)
    _require_org_member(request, org["id"])
    return orgs_mod.list_members(org["id"])


@router.patch("/orgs/{org_id}/members/{user_id}")
async def api_update_member_role(
    org_id: str, user_id: str, req: UpdateMemberRoleRequest, request: Request
):
    org = _resolve_org(org_id)
    actor_uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    try:
        member = orgs_mod.update_role(org["id"], user_id, req.role)
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    orgs_mod.log_audit(
        "member.role_change", org_id=org["id"], actor_user_id=actor_uid,
        resource_type="member", resource_id=user_id,
        metadata={"new_role": req.role},
        ip_addr=_client_ip(request),
    )
    return member


@router.delete("/orgs/{org_id}/members/{user_id}")
async def api_remove_member(org_id: str, user_id: str, request: Request):
    org = _resolve_org(org_id)
    actor_uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    try:
        ok = orgs_mod.remove_member(org["id"], user_id)
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    orgs_mod.log_audit(
        "member.remove", org_id=org["id"], actor_user_id=actor_uid,
        resource_type="member", resource_id=user_id,
        ip_addr=_client_ip(request),
    )
    return {"removed": ok}


@router.get("/orgs/{org_id}/invites")
async def api_list_invites(org_id: str, request: Request):
    org = _resolve_org(org_id)
    _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    return orgs_mod.list_invites(org["id"])


@router.post("/orgs/{org_id}/invites")
async def api_create_invite(org_id: str, req: CreateInviteRequest, request: Request):
    org = _resolve_org(org_id)
    uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    try:
        invite = orgs_mod.create_invite(
            org["id"], role=req.role, created_by=uid, ttl_days=req.ttl_days
        )
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    orgs_mod.log_audit(
        "member.invite", org_id=org["id"], actor_user_id=uid,
        resource_type="invite", resource_id=invite["id"],
        metadata={"role": invite["role"]},
        ip_addr=_client_ip(request),
    )
    return invite


@router.delete("/orgs/{org_id}/invites/{invite_id}")
async def api_revoke_invite(org_id: str, invite_id: str, request: Request):
    org = _resolve_org(org_id)
    uid, _ = _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    invite = orgs_mod.get_invite(invite_id)
    if not invite or invite.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Invite not found")
    ok = orgs_mod.revoke_invite(invite_id)
    orgs_mod.log_audit(
        "invite.revoke", org_id=org["id"], actor_user_id=uid,
        resource_type="invite", resource_id=invite_id,
        ip_addr=_client_ip(request),
    )
    return {"revoked": ok}


@router.get("/orgs/invites/{token}")
async def api_get_invite_by_token(token: str):
    """Public invite-preview endpoint — used by the accept page before signin."""
    invite = orgs_mod.get_invite_by_token(token)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    org = orgs_mod.get_org(invite["org_id"])
    return {
        "invite": {
            "id": invite["id"],
            "role": invite["role"],
            "expires_at": invite.get("expires_at"),
            "accepted_at": invite.get("accepted_at"),
            "revoked_at": invite.get("revoked_at"),
        },
        "org": {"id": org["id"], "slug": org["slug"], "name": org["name"]} if org else None,
    }


class AcceptInviteRequest(BaseModel):
    display_name: Optional[str] = ""


@router.post("/orgs/invites/{token}/accept")
async def api_accept_invite(
    token: str, request: Request, body: Optional[AcceptInviteRequest] = None,
):
    uid = _require_user(request)
    display_name = (body.display_name if body else "") or ""
    try:
        member = orgs_mod.accept_invite(token, uid, display_name=display_name.strip())
    except orgs_mod.OrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
    orgs_mod.log_audit(
        "invite.accept", org_id=member["org_id"], actor_user_id=uid,
        resource_type="member", resource_id=uid,
        metadata={"display_name": member.get("display_name") or ""},
        ip_addr=_client_ip(request),
    )
    return member


@router.get("/orgs/{org_id}/audit-logs")
async def api_list_audit_logs(
    org_id: str,
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    before: Optional[str] = None,
):
    org = _resolve_org(org_id)
    _require_org_role(request, org["id"], orgs_mod.ROLE_ADMIN)
    return orgs_mod.list_audit_logs(org["id"], limit=limit, before=before)


@router.get("/orgs/{org_id}/corpora")
async def api_list_org_corpora(org_id: str, request: Request):
    org = _resolve_org(org_id)
    _require_org_member(request, org["id"])
    rows = get_conn().execute(
        "SELECT * FROM corpora WHERE org_id=? ORDER BY updated_at DESC", (org["id"],)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("tags", "owned_handles", "task_types", "samples"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = _json.loads(d[k])
                except Exception:
                    pass
        out.append(d)
    return _annotate_compile_state(out)


