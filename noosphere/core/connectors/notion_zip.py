"""Notion export connector — one-shot import of a Notion workspace export ZIP.

Transient: each ZIP is a one-time import. Defaults to `user_original` since
the export is the user's own workspace. A future `notion_api` connector
will supersede this for live sync; the ZIP path remains as an offline
fallback and for users who don't want to grant API access.
"""

from pathlib import Path

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_USER_ORIGINAL,
)
from noosphere.core.importers import import_notion_export


class NotionZipConnector:
    kind = "notion_zip"
    default_source_kind = SOURCE_KIND_USER_ORIGINAL
    supports_incremental = False
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        zip_path = cfg.get("zip_path")
        if not zip_path:
            return {"ok": False, "detail": "zip_path required"}
        p = Path(zip_path)
        if not p.is_file():
            return {"ok": False, "detail": f"not a file: {zip_path}"}
        if p.suffix.lower() != ".zip":
            return {"ok": False, "detail": "expected .zip"}
        return {"ok": True, "detail": "ready"}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        zip_path = cfg.get("zip_path")
        result = ConnectorResult()
        try:
            out = import_notion_export(corpus_id, zip_path)
            result.fetched = out.get("total", 0)
            result.ingested = out.get("imported", 0)
            result.skipped = out.get("skipped", 0)
            result.detail = out
            if out.get("errors"):
                result.error = f"{out['errors']} entries failed to ingest"
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        return None
