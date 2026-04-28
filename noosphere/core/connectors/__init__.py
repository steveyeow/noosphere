"""Unified source adapters.

Two kinds of connector live here, behind a single ``Connector`` Protocol:

1. **Built-in Python connectors** (file upload, URL, RSS, directory sync,
   Twitter ZIP, Notion ZIP, chat capture) — sources whose mechanics don't
   benefit from a manifest abstraction (they read files, fetch URLs, parse
   ZIPs). These remain hand-written modules.
2. **Manifest-driven adapters** — sources that talk to external systems via
   standardised protocols (CLI, MCP, REST, email, file-snapshot). Configured
   by a TOML manifest in ``manifests/``; wrapped by ``ManifestConnector``.

Both register into the same ``REGISTRY`` and expose the same Protocol, so
the UI, scheduler, and audit log treat them identically. New sources of
the second kind are added by writing a manifest, not new Python code.
"""

from noosphere.core.connectors.base import (
    Connector,
    ConnectorResult,
    IngestDoc,
    SOURCE_KIND_EXTERNAL_PUBLIC,
    SOURCE_KIND_EXTERNAL_SUBSCRIPTION,
    SOURCE_KIND_USER_CAPTURE,
    SOURCE_KIND_USER_ORIGINAL,
)
from noosphere.core.connectors.chat_capture import ChatCaptureConnector
from noosphere.core.connectors.directory_sync import DirectorySyncConnector
from noosphere.core.connectors.file_upload import FileUploadConnector
from noosphere.core.connectors.manifest import (
    Manifest,
    ManifestConnector,
    ManifestError,
    discover_bundled_manifests,
    load_manifest,
)
from noosphere.core.connectors.notion_zip import NotionZipConnector
from noosphere.core.connectors.rss import RSSConnector
from noosphere.core.connectors.twitter_zip import TwitterZipConnector
from noosphere.core.connectors.url import URLConnector


# Built-in Python connectors. Order = default UI order in the Build tab.
_BUILTIN: tuple[Connector, ...] = (
    FileUploadConnector(),
    URLConnector(),
    RSSConnector(),
    DirectorySyncConnector(),
    TwitterZipConnector(),
    NotionZipConnector(),
    ChatCaptureConnector(),
)

# Manifest-driven adapters discovered at import time. Failures to parse a
# manifest are skipped silently (see ``discover_bundled_manifests``); they
# surface as test failures, not import failures.
_MANIFEST: tuple[Connector, ...] = tuple(discover_bundled_manifests())

# Manifest adapters render after built-ins in the UI by default.
_CONNECTORS: tuple[Connector, ...] = _BUILTIN + _MANIFEST

REGISTRY: dict[str, Connector] = {c.kind: c for c in _CONNECTORS}


def get(kind: str) -> Connector | None:
    """Look up a connector by kind."""
    return REGISTRY.get(kind)


def all_connectors() -> list[Connector]:
    """Return connectors in display order."""
    return list(_CONNECTORS)


def all_kinds() -> list[str]:
    """Return connector kinds in display order."""
    return [c.kind for c in _CONNECTORS]


__all__ = [
    "Connector",
    "ConnectorResult",
    "IngestDoc",
    "Manifest",
    "ManifestConnector",
    "ManifestError",
    "REGISTRY",
    "SOURCE_KIND_EXTERNAL_PUBLIC",
    "SOURCE_KIND_EXTERNAL_SUBSCRIPTION",
    "SOURCE_KIND_USER_CAPTURE",
    "SOURCE_KIND_USER_ORIGINAL",
    "all_connectors",
    "all_kinds",
    "discover_bundled_manifests",
    "get",
    "load_manifest",
]
