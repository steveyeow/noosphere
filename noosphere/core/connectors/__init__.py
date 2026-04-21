"""Unified source adapters.

Every external source (file upload, URL, RSS, Notion, Drive, GitHub, …) is
wrapped as a Connector. The abstraction lets the UI render all sources
uniformly in the Build tab, lets the scheduler poll auto-sync connectors in
one loop, and lets new sources plug in by implementing one Protocol.

This module exposes the base types and a registry of concrete connectors.
Existing ingestion functions in `noosphere.core.ingest`, `knowledge_growth`,
and `importers` keep working — connectors are thin adapters that delegate.
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
from noosphere.core.connectors.notion_zip import NotionZipConnector
from noosphere.core.connectors.rss import RSSConnector
from noosphere.core.connectors.twitter_zip import TwitterZipConnector
from noosphere.core.connectors.url import URLConnector


# Singleton registry — connectors are stateless so one instance each is enough.
# Order here is the default UI order in the Build tab "Add source" list.
_CONNECTORS: tuple[Connector, ...] = (
    FileUploadConnector(),
    URLConnector(),
    RSSConnector(),
    DirectorySyncConnector(),
    TwitterZipConnector(),
    NotionZipConnector(),
    ChatCaptureConnector(),
)

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
    "REGISTRY",
    "SOURCE_KIND_EXTERNAL_PUBLIC",
    "SOURCE_KIND_EXTERNAL_SUBSCRIPTION",
    "SOURCE_KIND_USER_CAPTURE",
    "SOURCE_KIND_USER_ORIGINAL",
    "all_connectors",
    "all_kinds",
    "get",
]
