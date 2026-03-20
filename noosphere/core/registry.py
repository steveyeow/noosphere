"""Registry client — auto-register corpora with a discovery registry."""

import logging

import httpx

from noosphere import __version__
from noosphere.core.config import NOOSPHERE_REGISTRY
from noosphere.core.corpus import list_corpora

log = logging.getLogger(__name__)


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
            }
            for c in public_corpora
        ],
    }

    try:
        resp = httpx.post(
            f"{registry.rstrip('/')}/api/v1/register",
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            log.info(f"Registered {len(public_corpora)} corpora with {registry}")
            return True
        else:
            log.warning(f"Registry returned {resp.status_code}: {resp.text[:200]}")
            return False
    except httpx.ConnectError:
        log.warning(f"Could not connect to registry at {registry} (will retry on next serve)")
        return False
    except Exception as e:
        log.warning(f"Registry registration failed: {e}")
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
