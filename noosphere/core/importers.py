"""Bulk importers for user-owned archives (Twitter, Notion, Obsidian vaults).

All imports default to source_kind="user_original" — the user is importing
THEIR OWN export/vault, not someone else's content. Per the Principle-3 copyright
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


_WIKILINK_PATTERN = re.compile(r"\[\[([^\[\]|#]+?)(?:#[^\[\]|]+)?(?:\|([^\[\]]+))?\]\]")
_HASHTAG_PATTERN = re.compile(r"(?:^|[\s(])#([A-Za-z][\w/\-]{1,63})")


def _parse_obsidian_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Obsidian frontmatter is YAML — but we only need tags, aliases, and scalars.

    Reuses a conservative line parser (same as ingest._extract_markdown_metadata)
    but additionally understands list syntax for `tags:` / `aliases:` — both
    Obsidian conventions — in two common shapes: inline `[a, b, c]` and block
    `- a\n- b\n`.
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, Any] = {}
    fm_lines = parts[1].strip().split("\n")
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        stripped = line.strip()
        if ":" not in stripped or stripped.startswith("#"):
            i += 1
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [s.strip().strip('"').strip("'") for s in val[1:-1].split(",")]
            meta[key] = [s for s in items if s]
        elif val == "" and i + 1 < len(fm_lines) and fm_lines[i + 1].lstrip().startswith("- "):
            block_items: list[str] = []
            j = i + 1
            while j < len(fm_lines) and fm_lines[j].lstrip().startswith("- "):
                block_items.append(fm_lines[j].lstrip()[2:].strip().strip('"').strip("'"))
                j += 1
            meta[key] = [s for s in block_items if s]
            i = j
            continue
        else:
            meta[key] = val.strip('"').strip("'")
        i += 1
    return meta, parts[2]


def import_obsidian_vault(corpus_id: str, zip_file_path: str | Path) -> dict[str, Any]:
    """Import an Obsidian vault (zipped folder of .md files) into a corpus.

    Preserves the parts of Obsidian that carry user intent:
      - folder path → metadata.folder_path, first segment as a tag
      - YAML frontmatter → tags + aliases + generic fields (dates, properties)
      - `#hashtags` in body → tags (merged with frontmatter tags)
      - `[[wikilinks]]` → metadata.wikilink_targets (list of target page names
        as the user wrote them; later entity-resolution passes can map these
        to canonical entities without losing the author's explicit intent)

    Vault subfolders starting with `.` (e.g. `.obsidian/`, `.trash/`) and
    macOS noise are skipped. Attachments (images, PDFs embedded in the vault)
    are ignored for v1 — users can re-upload important ones via regular upload.
    """
    zip_file_path = Path(zip_file_path)
    if not zip_file_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_file_path}")

    total = 0
    imported = 0
    skipped = 0
    errors = 0

    with zipfile.ZipFile(zip_file_path, "r") as zf:
        md_files = [
            n for n in zf.namelist()
            if n.lower().endswith(".md")
            and not n.startswith("__MACOSX")
            and "/." not in ("/" + n)
            and not n.split("/")[-1].startswith(".")
        ]
        total = len(md_files)

        for filepath in md_files:
            parts = filepath.split("/")
            # Strip the common vault-root prefix Obsidian ZIPs always carry
            # (e.g. "my-vault/notes/foo.md" → folder "notes", file "foo.md").
            rel_parts = parts[1:] if len(parts) > 1 else parts
            filename = Path(rel_parts[-1]).stem
            folder = "/".join(rel_parts[:-1])

            try:
                raw = zf.read(filepath).decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed to read %s from ZIP: %s", filepath, e)
                errors += 1
                continue

            if not raw.strip():
                skipped += 1
                continue

            fm, body = _parse_obsidian_frontmatter(raw)
            if not body.strip():
                skipped += 1
                continue

            title = (fm.get("title") or "").strip() or filename

            tags: list[str] = ["obsidian"]
            fm_tags = fm.get("tags") or fm.get("tag") or []
            if isinstance(fm_tags, str):
                tags.extend([t.strip() for t in fm_tags.split(",") if t.strip()])
            elif isinstance(fm_tags, list):
                tags.extend([str(t).strip() for t in fm_tags if str(t).strip()])
            for m in _HASHTAG_PATTERN.finditer(body):
                tags.append(m.group(1))
            if folder:
                tags.append(folder.split("/")[0])
            # Dedup while preserving order
            seen: set[str] = set()
            tags = [t for t in tags if not (t in seen or seen.add(t))]

            wikilink_targets: list[str] = []
            for m in _WIKILINK_PATTERN.finditer(body):
                target = m.group(1).strip()
                if target and target not in wikilink_targets:
                    wikilink_targets.append(target)

            aliases = fm.get("aliases") or fm.get("alias")
            if isinstance(aliases, str):
                aliases = [a.strip() for a in aliases.split(",") if a.strip()]
            elif not isinstance(aliases, list):
                aliases = []

            meta: dict[str, Any] = {
                "source": "obsidian_vault",
                "original_path": filepath,
                "folder_path": folder,
                "wikilink_targets": wikilink_targets,
            }
            if aliases:
                meta["aliases"] = aliases
            for k in ("created", "updated", "date", "author"):
                if k in fm and fm[k]:
                    meta[k] = fm[k]

            try:
                ingest_text(
                    corpus_id,
                    title=title,
                    content=body,
                    doc_type="note",
                    source_kind="user_original",
                    tags=tags,
                    metadata=meta,
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to ingest Obsidian note %s: %s", title, e)
                errors += 1

    if imported > 0:
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("Index after Obsidian import failed: %s", e)

    return {
        "total": total,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "source_kind": "user_original",
    }
