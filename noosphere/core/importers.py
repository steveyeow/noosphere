"""Bulk importers for user-owned archives (Twitter data export, Notion workspace export).

Both imports default to source_kind="user_original" — the user is importing
THEIR OWN export, not someone else's content. Per the Principle-3 copyright
rule in project_noosphere_ingestion: only user-created content is monetizable,
so correct source_kind attribution on bulk imports matters.
"""

from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from noosphere.core.indexer import index_corpus
from noosphere.core.ingest import _html_to_markdown, ingest_text

logger = logging.getLogger(__name__)


_BATCH_SIZE = 50


def import_twitter_archive(corpus_id: str, zip_file_path: str | Path) -> dict[str, Any]:
    """Import a Twitter / X data export ZIP into a corpus.

    Expects the standard Twitter archive format: data/tweets.js or data/tweet.js
    containing `window.YTD.tweet.part0 = [...]`.

    Every tweet is ingested as source_kind=user_original (they're the user's
    own tweets from their own export) with doc_type=tweet.
    """
    zip_file_path = Path(zip_file_path)
    if not zip_file_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_file_path}")

    with zipfile.ZipFile(zip_file_path, "r") as zf:
        candidates = [n for n in zf.namelist() if n.endswith("tweets.js") or n.endswith("tweet.js")]
        if not candidates:
            raise ValueError("No tweets.js found in archive. Expected data/tweets.js")
        raw = zf.read(candidates[0]).decode("utf-8", errors="replace")

    # Strip the JS variable assignment prefix (e.g. "window.YTD.tweet.part0 = ")
    match = re.match(r"^[^=]+=\s*", raw)
    if match:
        raw = raw[match.end():]
    try:
        tweets_data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse tweets.js: {e}") from e
    if not tweets_data:
        raise ValueError("No tweets found in archive")

    total = len(tweets_data)
    imported = 0
    skipped = 0
    errors = 0

    for i in range(0, total, _BATCH_SIZE):
        batch = tweets_data[i : i + _BATCH_SIZE]
        for entry in batch:
            tweet = entry.get("tweet", entry) if isinstance(entry, dict) else {}
            text = tweet.get("full_text", "") or tweet.get("text", "")
            if not text.strip():
                skipped += 1
                continue

            tweet_id = str(tweet.get("id_str", tweet.get("id", "")))
            created_at = tweet.get("created_at", "")
            retweet_count = tweet.get("retweet_count", 0)
            favorite_count = tweet.get("favorite_count", 0)

            title = text[:80].replace("\n", " ").strip() or f"Tweet {tweet_id}"
            meta = {
                "tweet_id": tweet_id,
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
                    source_kind="user_original",
                    date=created_at[:10] if created_at else "",
                    tags=["twitter", "tweet"],
                    metadata=meta,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to ingest tweet %s: %s", tweet_id, e)
                errors += 1

    if imported > 0:
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("Index after twitter import failed: %s", e)

    return {
        "total": total,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "source_kind": "user_original",
    }


_NOTION_UUID_SUFFIX = re.compile(r"\s+[a-f0-9]{32}$")


def import_notion_export(corpus_id: str, zip_file_path: str | Path) -> dict[str, Any]:
    """Import a Notion workspace export ZIP into a corpus.

    Walks the directory tree inside the ZIP and ingests .md / .html / .csv files.
    Notion's UUID suffix on page titles (e.g. "My Page abc123def456...") is stripped.

    Defaults all pages to source_kind=user_original — Notion is the user's own
    workspace. Users can re-tag individual docs later if needed.
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
            title = _NOTION_UUID_SUFFIX.sub("", filename).strip() or filename

            try:
                raw = zf.read(filepath).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed to read %s from ZIP: %s", filepath, e)
                errors += 1
                continue

            if not raw.strip():
                skipped += 1
                continue

            if ext in (".html", ".htm"):
                body = _html_to_markdown(raw)
            else:
                body = raw

            if not body.strip():
                skipped += 1
                continue

            doc_type = "data" if ext == ".csv" else "note"
            meta = {
                "source": "notion_export",
                "original_path": filepath,
            }

            try:
                ingest_text(
                    corpus_id,
                    title=title,
                    content=body,
                    doc_type=doc_type,
                    source_kind="user_original",
                    tags=["notion"],
                    metadata=meta,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to ingest Notion page %s: %s", title, e)
                errors += 1

    if imported > 0:
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("Index after Notion import failed: %s", e)

    return {
        "total": total,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "source_kind": "user_original",
    }
