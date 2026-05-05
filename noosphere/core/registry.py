"""Registry client — auto-register corpora with a discovery registry.

The registry endpoint ``/api/v1/register`` takes a full snapshot of a node's
non-private corpora and reconciles its record (adds new, updates changed,
deletes missing). Calling this once at ``serve`` startup is not enough —
if corpora are created, updated, or deleted at runtime, the registry goes
stale. ``resync_registry()`` is the hook that runs on every mutation so
``noosphere.wiki`` always reflects the live state.
"""

import logging

import httpx

from noosphere import __version__
from noosphere.core.config import NOOSPHERE_REGISTRY
from noosphere.core.corpus import list_corpora, source_composition

log = logging.getLogger(__name__)

# Module-level state: the endpoint URL this node was launched with. Set by
# `serve` on startup via set_node_endpoint(); read by resync_registry() when
# a corpus mutation needs to push updated state. Stays None in contexts
# where no server is running (e.g. `noosphere init` in isolation) — resync
# then quietly no-ops.
_NODE_ENDPOINT: str | None = None

# Remember whether the last `register_with_registry()` call actually
# succeeded (HTTP 200/201 from the registry). The /health endpoint reports
# this so the UI can show a trustworthy status: a HEAD probe succeeding
# doesn't prove registration works (auth, rate limits, or middleware can
# still reject the POST), so a dedicated signal is more reliable.
_LAST_REGISTRATION_OK: bool = False


def set_node_endpoint(endpoint: str) -> None:
    """Remember the node's public endpoint URL so runtime corpus mutations
    can trigger registry resyncs without re-plumbing it through every call
    site. Called once from the `serve` command."""
    global _NODE_ENDPOINT
    _NODE_ENDPOINT = endpoint.rstrip("/")


def last_registration_ok() -> bool:
    """Whether the most recent register_with_registry() call succeeded.
    Safer than a HEAD probe for UI status — probe can succeed while the
    actual POST is blocked by auth or other middleware."""
    return _LAST_REGISTRATION_OK


def is_local_endpoint(url: str) -> bool:
    """True for endpoint URLs that aren't reachable from outside the host.

    A self-hosted node advertising `http://localhost:8420` to the shared
    registry is useless — federation queries to that URL hit the requester's
    own machine, not ours. Worse, the registry then thinks our public
    corpora are reachable when they aren't. Detect and skip these so dev
    instances (and `noosphere serve` without --public-url) don't pollute
    the network with dead pointers. Covers the full 127.0.0.0/8 loopback
    range (not just 127.0.0.1) and IPv6 localhost.
    """
    if not url or not url.strip():
        return True
    from urllib.parse import urlparse
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
    except Exception:
        return True
    if not host:
        return True
    return (
        host in ("localhost", "0.0.0.0", "::1")
        or host.startswith("127.")
        or host.endswith(".localhost")
    )


def resync_registry() -> bool:
    """Re-push the current non-private corpora snapshot to the discovery
    registry. Safe to call from any corpus mutation — no-op if the node
    has no endpoint configured (no `serve` yet), no-op if registry is
    disabled (``NOOSPHERE_REGISTRY=none``), never raises.

    Use from FastAPI routes as a background task (``background_tasks.add_task``)
    so the registry round-trip doesn't block the user's mutation response.
    """
    if not _NODE_ENDPOINT:
        return False
    try:
        return register_with_registry(_NODE_ENDPOINT)
    except Exception as e:
        log.warning("resync_registry failed: %s", e)
        return False


def register_with_registry(
    endpoint_url: str,
    *,
    registry_url: str = "",
) -> bool:
    """Register all public corpora with the discovery registry.

    Args:
        endpoint_url: The publicly accessible URL of this Noosphere node.
        registry_url: Registry URL (uses NOOSPHERE_REGISTRY config if empty).

    Returns:
        True if registration succeeded, False otherwise.
    """
    registry = registry_url or NOOSPHERE_REGISTRY
    if not registry:
        log.info("Registry disabled (NOOSPHERE_REGISTRY=none)")
        return False

    if is_local_endpoint(endpoint_url):
        log.info(
            "Skipping registry POST: endpoint %s is not publicly reachable. "
            "Set APP_URL (or noosphere serve --public-url) to a public URL "
            "to join the network.",
            endpoint_url,
        )
        return False

    corpora = list_corpora()
    public_corpora = [c for c in corpora if c.get("access_level") != "private"]

    if not public_corpora:
        log.info("No public corpora to register")
        return True

    payload = {
        "node_version": __version__,
        "endpoint": endpoint_url.rstrip("/"),
        "corpora": [
            {
                "corpus_id": c["id"],
                "name": c["name"],
                "slug": c.get("slug", ""),
                "description": c.get("description", ""),
                "author": c.get("author_name", ""),
                "tags": c.get("tags", []),
                "document_count": c.get("document_count", 0),
                "chunk_count": c.get("chunk_count", 0),
                "word_count": c.get("word_count", 0),
                "access_level": c.get("access_level", "public"),
                "status": c.get("status", "draft"),
                "task_types": c.get("task_types", []),
                "autonomy_level": c.get("autonomy_level", 0),
                "source_composition": source_composition(c["id"]),
                "kb_reputation": c.get("kb_reputation", 0.0) or 0.0,
            }
            for c in public_corpora
        ],
    }

    global _LAST_REGISTRATION_OK
    try:
        resp = httpx.post(
            f"{registry.rstrip('/')}/api/v1/register",
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            log.info(f"Registered {len(public_corpora)} corpora with {registry}")
            _LAST_REGISTRATION_OK = True
            return True
        else:
            log.warning(f"Registry returned {resp.status_code}: {resp.text[:200]}")
            _LAST_REGISTRATION_OK = False
            return False
    except httpx.ConnectError:
        log.warning(f"Could not connect to registry at {registry} (will retry on next serve)")
        _LAST_REGISTRATION_OK = False
        return False
    except Exception as e:
        log.warning(f"Registry registration failed: {e}")
        _LAST_REGISTRATION_OK = False
        return False


def deregister_from_registry(
    endpoint_url: str,
    *,
    registry_url: str = "",
) -> bool:
    """Remove this node's corpora from the registry."""
    registry = registry_url or NOOSPHERE_REGISTRY
    if not registry:
        return False

    try:
        resp = httpx.post(
            f"{registry.rstrip('/')}/api/v1/deregister",
            json={"endpoint": endpoint_url.rstrip("/")},
            timeout=10,
        )
        return resp.status_code in (200, 204)
    except Exception:
        return False
