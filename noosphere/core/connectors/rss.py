"""RSS/Atom feed connector — scheduled incremental pull from a feed URL.

Persistent: one instance per subscribed feed. Delegates to
`ingest_rss_feed` which dedupes by guid/link against prior entries, so the
connector is safely re-runnable. This is the canonical example of an
incremental connector that also auto-syncs on a cron.
"""

from noosphere.core.connectors.base import (
    ConnectorResult,
    SOURCE_KIND_EXTERNAL_PUBLIC,
)
from noosphere.core.knowledge_growth import ingest_rss_feed


class RSSConnector:
    kind = "rss"
    default_source_kind = SOURCE_KIND_EXTERNAL_PUBLIC
    supports_incremental = True
    supports_oauth = False

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        feed_url = cfg.get("feed_url")
        if not feed_url or not isinstance(feed_url, str):
            return {"ok": False, "detail": "feed_url required"}
        if not feed_url.startswith("http"):
            return {"ok": False, "detail": "feed_url must be http(s)"}
        return {"ok": True, "detail": "feed URL accepted"}

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since=None,
    ) -> ConnectorResult:
        feed_url = cfg.get("feed_url")
        max_items = int(cfg.get("max_items", 25))
        result = ConnectorResult()
        try:
            out = ingest_rss_feed(corpus_id, feed_url, max_items=max_items)
            ingested = out.get("ingested", 0)
            skipped = out.get("skipped", 0)
            result.fetched = ingested + skipped
            result.ingested = ingested
            result.skipped = skipped
            result.detail = {"feed_url": feed_url, **{k: v for k, v in out.items() if k not in ("documents",)}}
        except Exception as e:
            result.error = str(e)
        return result

    def default_cron(self) -> str | None:
        # Poll every 6 hours by default; user may override per instance.
        return "0 */6 * * *"
