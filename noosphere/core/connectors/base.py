"""Connector Protocol and shared types.

A Connector is an adapter for one kind of source (file upload, URL, RSS,
Notion, Drive, GitHub, …). Every connector exposes four capabilities:

1. Static metadata (`kind`, `default_source_kind`, `supports_incremental`,
   `supports_oauth`) — used by the UI to render and by the scheduler to
   decide whether to auto-run.
2. `test_connection` — validate cfg + credentials before saving or a
   scheduled run, so revoked tokens and bad configs fail fast.
3. `run` — execute one full or incremental sync against a corpus, returning
   a ConnectorResult. The Protocol is intentionally pragmatic: connectors
   may either produce IngestDocs and route them through the ingest pipeline,
   or delegate to an existing `ingest_*` function. The caller only cares
   about the result.
4. `default_cron` — optional schedule for auto-sync. One-shot connectors
   (file upload, ZIP import) return None; RSS/Notion/Drive return a cron
   string the user can override per instance.

Connectors are stateless: all per-instance state lives in the `connectors`
table (cfg, credentials, last_sync_at). The Protocol is duck-typed —
concrete connectors live in sibling modules and don't inherit anything.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


# Mirrors the documents.source_kind column. Connectors declare a default on
# the class; individual IngestDocs may override.
SOURCE_KIND_USER_ORIGINAL = "user_original"
SOURCE_KIND_USER_CAPTURE = "user_capture"
SOURCE_KIND_EXTERNAL_PUBLIC = "external_public"
SOURCE_KIND_EXTERNAL_SUBSCRIPTION = "external_subscription"


@dataclass
class IngestDoc:
    """Normalized document shape for connectors that use the yield pattern
    internally (typical for T1+ OAuth connectors like Notion/Drive/GitHub).

    Legacy connectors that wrap existing `ingest_*` functions don't need to
    build IngestDocs — they just invoke the function. IngestDoc is a helper,
    not a Protocol requirement.
    """

    content: str
    title: str | None = None
    source_url: str | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    source_kind: str | None = None
    external_id: str | None = None
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorResult:
    """Outcome of one run(). Surfaces in the Build tab status and audit log."""

    fetched: int = 0
    ingested: int = 0
    updated: int = 0
    skipped: int = 0
    error: str | None = None
    next_sync_at: datetime | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Connector(Protocol):
    """A source adapter. See module docstring."""

    kind: str
    default_source_kind: str
    supports_incremental: bool
    supports_oauth: bool

    def test_connection(
        self, cfg: dict, credentials: dict | None = None
    ) -> dict:
        """Return {ok: bool, detail: str, preview?: Any}.

        Called before saving a connector instance and before each scheduled
        run. Connectors without credentials (file upload, URL, RSS) still
        implement this to validate cfg shape.
        """
        ...

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since: datetime | None = None,
    ) -> ConnectorResult:
        """Execute one sync/ingest.

        If the connector supports incremental and `since` is given, only
        new/changed content is processed. Implementations may route through
        the ingest pipeline themselves or delegate to existing ingest_*
        functions — callers only care about the ConnectorResult.
        """
        ...

    def default_cron(self) -> str | None:
        """APScheduler cron expression, or None for manual-only connectors."""
        ...
