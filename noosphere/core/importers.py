"""Importers for structured data exports — Twitter archive, Notion export."""

from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from noosphere.core.ingest import ingest_text, _html_to_markdown
from noosphere.core.indexer import index_corpus

logger = logging.getLogger(__name__)


def import_twitter_archive(corpus_id: str, zip_file_path: str | Path) -> dict[str, Any]:
    """Import a Twitter/X data archive ZIP into a corpus.

    Expects the standard Twitter archive format with data/tweets.js
    (or data/tweet.js) containing `window.YTD.tweet.part0 = [...]`.
    """
    zip_file_path = Path(zip_file_path)
    if not zip_file_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_file_path}")

    tweets_data = None
    with zipfile.ZipFile(zip_file_path, "r") as zf:
        # Twitter archive stores tweets in data/tweets.js or data/tweet.js
        candidates = [n for n in zf.namelist() if n.endswith("tweets.js") or n.endswith("tweet.js")]
        if not candidates:
            raise ValueError("No tweets.js found in archive. Expected data/tweets.js")

        raw = zf.read(candidates[0]).decode("utf-8", errors="replace")
        # Strip the JS variable assignment prefix
        match = re.match(r"^[^=]+=\s*", raw)
        if match:
            raw = raw[match.end():]
        tweets_data = json.loads(raw)

    if not tweets_data:
        raise ValueError("No tweets found in archive")

    total = len(tweets_data)
    imported = 0
    skipped = 0
    errors = 0
    batch_size = 50

    for i in range(0, total, batch_size):
        batch = tweets_data[i : i + batch_size]
        for entry in batch:
            tweet = entry.get("tweet", entry)
            text = tweet.get("full_text", "") or tweet.get("text", "")
            if not text.strip():
                skipped += 1
                continue

            tweet_id = tweet.get("id_str", tweet.get("id", ""))
            created_at = tweet.get("created_at", "")
            retweet_count = tweet.get("retweet_count", 0)
            favorite_count = tweet.get("favorite_count", 0)

            title = text[:80].replace("\n", " ").strip()
            meta = {
                "tweet_id": str(tweet_id),
                "created_at": created_at,
                "retweet_count": int(retweet_count) if retweet_count else 0,
                "favorite_count": int(favorite_count) if favorite_count else 0,
                "source": "twitter_archive",
            }

            try:
                ingest_text(
                    corpus_id,
                    title=title,
                    content=text,
                    doc_type="tweet",
                    date=created_at[:10] if created_at else "",
                    tags=["twitter", "tweet"],
                    metadata=meta,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to ingest tweet %s: %s", tweet_id, e)
                errors += 1

        # Index after each batch
        if imported > 0:
            try:
                index_corpus(corpus_id)
            except Exception as e:
                logger.warning("Index after twitter batch failed: %s", e)

    return {"total": total, "imported": imported, "skipped": skipped, "errors": errors}


def import_notion_export(corpus_id: str, zip_file_path: str | Path) -> dict[str, Any]:
    """Import a Notion workspace export ZIP into a corpus.

    Walks the directory tree inside the ZIP, ingesting .md and .html files.
    Strips Notion's UUID suffix from page titles.
    """
    zip_file_path = Path(zip_file_path)
    if not zip_file_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_file_path}")

    total = 0
    imported = 0
    skipped = 0
    errors = 0

    with zipfile.ZipFile(zip_file_path, "r") as zf:
        content_files = [
            n for n in zf.namelist()
            if (n.endswith(".md") or n.endswith(".html") or n.endswith(".csv"))
            and not n.startswith("__MACOSX")
            and not n.split("/")[-1].startswith(".")
        ]
        total = len(content_files)

        for filepath in content_files:
            filename = Path(filepath).stem
            ext = Path(filepath).suffix.lower()

            # Strip Notion's UUID suffix (format: "Page Name abc123def456")
            title = re.sub(r"\s+[a-f0-9]{32}$", "", filename).strip()
            if not title:
                title = filename

            try:
                raw_content = zf.read(filepath).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed to read %s from ZIP: %s", filepath, e)
                errors += 1
                continue

            if not raw_content.strip():
                skipped += 1
                continue

            # Convert HTML to markdown if needed
            if ext in (".html", ".htm"):
                body = _html_to_markdown(raw_content)
            elif ext == ".csv":
                # Basic CSV ingestion — store as-is with data doc_type
                body = raw_content
            else:
                body = raw_content

            if not body.strip():
                skipped += 1
                continue

            meta = {
                "source": "notion_export",
                "original_path": filepath,
            }
            doc_type = "data" if ext == ".csv" else "note"

            try:
                ingest_text(
                    corpus_id,
                    title=title,
                    content=body,
                    doc_type=doc_type,
                    tags=["notion"],
                    metadata=meta,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to ingest Notion page %s: %s", title, e)
                errors += 1

    # Final index
    if imported > 0:
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("Index after Notion import failed: %s", e)

    return {"total": total, "imported": imported, "skipped": skipped, "errors": errors}
