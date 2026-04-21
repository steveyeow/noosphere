"""Directory sync connector — incremental sync from a local directory.

Persistent connector (one instance per watched directory). Delegates to
`sync_directory` which compares file content hashes against stored
documents, adding new, updating changed, and optionally pruning removed.
Used today via CLI `noosphere sync`; exposed to the Build tab UI for
self-hosted runs and eventually scheduled syncs.
"""

from pathlib import Path

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_USER_ORIGINAL,
)
from noosphere.core.ingest import sync_directory


class DirectorySyncConnector:
    kind = "directory_sync"
    default_source_kind = SOURCE_KIND_USER_ORIGINAL
    supports_incremental = True
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        directory = cfg.get("directory")
        if not directory:
            return {"ok": False, "detail": "directory required"}
        p = Path(directory)
        if not p.is_dir():
            return {"ok": False, "detail": f"not a directory: {directory}"}
        return {"ok": True, "detail": "readable", "preview": {"path": str(p.resolve())}}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        directory = cfg.get("directory")
        prune = bool(cfg.get("prune", False))
        doc_type = cfg.get("doc_type", "doc")
        result = ConnectorResult()
        try:
            counts = sync_directory(
                corpus_id, directory, doc_type=doc_type, prune=prune
            )
            result.fetched = (
                counts.get("new", 0)
                + counts.get("updated", 0)
                + counts.get("unchanged", 0)
            )
            result.ingested = counts.get("new", 0)
            result.updated = counts.get("updated", 0)
            result.skipped = counts.get("unchanged", 0) + counts.get("pruned", 0)
            result.detail = counts
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        return None
