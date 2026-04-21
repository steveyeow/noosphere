"""Chat capture connector — save text from a chat session as a corpus doc.

Transient: each capture is a one-shot save. source_kind=user_capture
preserves provenance: the content was user-authored or user-curated during
a chat session, distinct from both primary user_original docs and
external_public ingested content.
"""

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_USER_CAPTURE,
)
from noosphere.core.knowledge_growth import save_capture


class ChatCaptureConnector:
    kind = "chat_capture"
    default_source_kind = SOURCE_KIND_USER_CAPTURE
    supports_incremental = False
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        if not (cfg.get("content") or "").strip():
            return {"ok": False, "detail": "content required"}
        return {"ok": True, "detail": "ready"}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        result = ConnectorResult()
        try:
            doc = save_capture(
                corpus_id,
                content=cfg.get("content", ""),
                title=cfg.get("title", ""),
                question=cfg.get("question", ""),
                session_id=cfg.get("session_id", ""),
            )
            result.fetched = 1
            result.ingested = 1
            result.detail = {"document_id": doc.get("id")}
        except ValueError as e:
            result.skipped = 1
            result.error = str(e)
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        return None
