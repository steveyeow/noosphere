"""URL connector — fetch HTTP page(s), convert HTML to markdown, ingest.

Transient: each run is a one-shot fetch of one or more URLs. cfg accepts
either `url` (single) or `urls` (batch) for compatibility with the
existing `/corpora/{id}/ingest-url` and `/ingest-urls` routes. Default
source_kind is `external_public`, auto-upgraded to `user_original` at the
`ingest_url` layer if the URL matches the corpus's owned_handles.
"""

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_EXTERNAL_PUBLIC,
)
from noosphere.core.ingest import ingest_url
from noosphere.core.knowledge_growth import ingest_urls_bulk


class URLConnector:
    kind = "url"
    default_source_kind = SOURCE_KIND_EXTERNAL_PUBLIC
    supports_incremental = False
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        url = cfg.get("url")
        urls = cfg.get("urls")
        if not url and not urls:
            return {"ok": False, "detail": "url or urls required"}
        if url and not isinstance(url, str):
            return {"ok": False, "detail": "url must be a string"}
        if urls and not isinstance(urls, list):
            return {"ok": False, "detail": "urls must be a list"}
        for u in [url] if url else urls:
            if not isinstance(u, str) or not u.startswith("http"):
                return {"ok": False, "detail": f"invalid URL: {u}"}
        return {"ok": True, "detail": "ready"}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        doc_type = cfg.get("doc_type", "blog")
        source_kind = cfg.get("source_kind")
        result = ConnectorResult()
        try:
            if cfg.get("urls"):
                out = ingest_urls_bulk(
                    corpus_id, cfg["urls"],
                    doc_type=doc_type, source_kind=source_kind,
                )
                result.fetched = out.get("ingested", 0) + out.get("failed", 0)
                result.ingested = out.get("ingested", 0)
                result.skipped = out.get("failed", 0)
                result.detail = {"errors": out.get("errors", [])}
            else:
                doc = ingest_url(
                    corpus_id, cfg["url"],
                    doc_type=doc_type, source_kind=source_kind,
                )
                result.fetched = 1
                result.ingested = 1 if doc else 0
                if doc:
                    result.detail = {"document_id": doc.get("id")}
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        return None
