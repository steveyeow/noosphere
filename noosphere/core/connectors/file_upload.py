"""File upload connector — transient single-file ingestion.

No persistent row in the `connectors` table; the connector exists to
classify file uploads with a uniform source_kind and surface under the
Build tab's "Ways to add knowledge" list. `run` delegates to the existing
`ingest_file` so the hot path through `/corpora/{id}/upload` is untouched.
"""

from pathlib import Path

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_USER_ORIGINAL,
)
from noosphere.core.ingest import SUPPORTED_FILE_EXTENSIONS, ingest_file


class FileUploadConnector:
    kind = "file_upload"
    default_source_kind = SOURCE_KIND_USER_ORIGINAL
    supports_incremental = False
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        filepath = cfg.get("filepath")
        if not filepath:
            return {"ok": False, "detail": "filepath required"}
        p = Path(filepath)
        if not p.is_file():
            return {"ok": False, "detail": f"not a file: {filepath}"}
        if p.suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
            return {"ok": False, "detail": f"unsupported extension: {p.suffix}"}
        return {"ok": True, "detail": "ready"}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        filepath = cfg.get("filepath")
        doc_type = cfg.get("doc_type", "doc")
        result = ConnectorResult()
        try:
            doc = ingest_file(corpus_id, filepath, doc_type=doc_type)
            if doc:
                result.fetched = 1
                result.ingested = 1
                result.detail = {"document_id": doc.get("id")}
            else:
                result.skipped = 1
                result.detail = {"reason": "empty or unparseable"}
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        return None
