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


def import_twitter_archive(
    corpus_id: str,
    zip_file_path: str | Path,
    *,
    contributor_user_id: str | None = None,
) -> dict[str, Any]:
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
                    contributor_user_id=contributor_user_id,
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


def import_notion_export(
    corpus_id: str,
    zip_file_path: str | Path,
    *,
    contributor_user_id: str | None = None,
) -> dict[str, Any]:
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
                    contributor_user_id=contributor_user_id,
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


# ── GBrain repo importer ─────────────────────────────────────────────
#
# GBrain (github.com/garrytan/gbrain) is a directory of markdown files, one
# page per entity, organized by typed folders (people/ companies/ concepts/
# meetings/ ...). Each page is YAML frontmatter, then "compiled truth", then
# a `---`, then an append-only timeline. That maps almost 1:1 onto Noosphere:
# people/companies → entities whose `description` IS the compiled truth;
# concepts/ → Wiki concept docs; everything else → source docs. The full page
# is also ingested as a document so the timeline stays searchable and shows
# under the entity's related-docs.

# gbrain structural / agent-facing files that are not knowledge pages.
_GBRAIN_SKIP_FILENAMES = {
    "index.md", "log.md", "resolver.md", "schema.md", "readme.md",
    "agents.md", "claude.md", "gbrain_recommended_schema.md",
}
# Top-level folders we deliberately do not ingest.
_GBRAIN_SKIP_FOLDERS = {"archive"}
# A markdown link whose target is another .md page: [text](../people/foo.md)
_MD_PAGE_LINK_PATTERN = re.compile(r"\]\(\s*([^)\s]+\.md)(?:#[^)]*)?\s*\)")
# A line that is exactly a markdown horizontal rule (the truth|timeline split).
_GBRAIN_HR = re.compile(r"^\s*-{3,}\s*$")


def _gbrain_title(fm: dict[str, Any], body: str, slug: str) -> str:
    """Prefer frontmatter title, then the first `# H1`, then a humanized slug."""
    t = (fm.get("title") or "").strip()
    if t:
        return t
    for line in body.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return slug.replace("-", " ").replace("_", " ").strip().title() or slug


def _gbrain_split_truth_timeline(body: str) -> tuple[str, str]:
    """Split a gbrain page body into (compiled_truth, timeline).

    The split is the first standalone horizontal-rule line after the
    (already-stripped) frontmatter. No rule → the whole body is truth.
    """
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _GBRAIN_HR.match(line):
            truth = "\n".join(lines[:i]).strip()
            timeline = "\n".join(lines[i + 1:]).strip()
            return truth, timeline
    return body.strip(), ""


def _gbrain_strip_h1(text: str) -> str:
    """Drop a leading `# Heading` — on a gbrain entity page it is just the
    entity's own name, which the entity page already shows as its title.
    Keeps the compiled-truth block from repeating the name."""
    lines = text.lstrip().splitlines()
    if lines and re.match(r"^#\s+\S", lines[0]):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def _gbrain_aliases(fm: dict[str, Any]) -> list[str]:
    a = fm.get("aliases") or fm.get("alias")
    if isinstance(a, str):
        return [s.strip() for s in a.split(",") if s.strip()]
    if isinstance(a, list):
        return [str(s).strip() for s in a if str(s).strip()]
    return []


def import_gbrain_repo(
    corpus_id: str,
    root_dir: str | Path,
    *,
    contributor_user_id: str | None = None,
) -> dict[str, Any]:
    """Import a GBrain repo directory into a corpus at full fidelity.

    Mapping:
      - people/<slug>.md       → entity kind=person; description = compiled truth
      - companies/<slug>.md    → entity kind=organization; description = compiled truth
      - concepts/<slug>.md     → doc_type=concept (Wiki section)
      - everything else        → source document

    For people/companies the full page (truth + timeline) is also ingested as
    a document linked to the entity (metadata.mentioned_entity_ids) so the
    timeline is searchable and appears on the entity page.

    Second pass resolves gbrain cross-links — markdown `*.md` links and
    `[[wikilinks]]` — by filename slug or name to entity ids.

    Everything lands as source_kind=user_original — a gbrain repo is the
    user's own brain.
    """
    from noosphere.core.db import get_conn
    from noosphere.core.entities import upsert_entity

    root = Path(root_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    # Dot-dirs (.raw/ .git/ ...) are sidecar/noise — excluded from
    # consideration entirely. Recognized gbrain meta files ARE counted as
    # skipped so the import result is honest about what was left out.
    md_files = sorted(
        p for p in root.rglob("*.md")
        if p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )

    total = len(md_files)
    entities_made = 0
    concepts = 0
    sources = 0
    skipped = 0
    errors = 0

    slug_to_eid: dict[str, str] = {}
    name_to_eid: dict[str, str] = {}
    # (doc_id, body, own_entity_id|None) for the cross-link pass.
    link_targets: list[tuple[str, str, str | None]] = []

    for fp in md_files:
        rel = fp.relative_to(root)
        parts = rel.parts
        folder = parts[0].lower() if len(parts) > 1 else ""
        if fp.name.lower() in _GBRAIN_SKIP_FILENAMES:
            skipped += 1
            continue
        if folder in _GBRAIN_SKIP_FOLDERS:
            skipped += 1
            continue

        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("gbrain: cannot read %s: %s", rel, e)
            errors += 1
            continue
        if not raw.strip():
            skipped += 1
            continue

        fm, body = _parse_obsidian_frontmatter(raw)
        body = body.strip()
        if not body:
            skipped += 1
            continue

        slug = fp.stem
        title = _gbrain_title(fm, body, slug)
        meta: dict[str, Any] = {
            "source": "gbrain",
            "original_path": str(rel),
            "gbrain_slug": slug,
        }

        try:
            if folder in ("people", "person"):
                kind = "person"
            elif folder in ("companies", "company"):
                kind = "organization"
            else:
                kind = ""

            if kind:
                truth, _timeline = _gbrain_split_truth_timeline(body)
                aliases = _gbrain_aliases(fm)
                eid = upsert_entity(
                    corpus_id, kind, title,
                    aliases=aliases,
                    description=_gbrain_strip_h1(truth),
                    metadata={"source": "gbrain", "gbrain_slug": slug,
                              "original_path": str(rel)},
                )
                if not eid:
                    skipped += 1
                    continue
                entities_made += 1
                slug_to_eid[slug.lower()] = eid
                name_to_eid.setdefault(title.lower(), eid)
                for al in aliases:
                    name_to_eid.setdefault(al.lower(), eid)

                doc_meta = {**meta, "gbrain_kind": kind,
                            "mentioned_entity_ids": [eid]}
                doc = ingest_text(
                    corpus_id, title=title, content=body, doc_type="note",
                    source_kind="user_original",
                    tags=["gbrain", folder],
                    metadata=doc_meta,
                    contributor_user_id=contributor_user_id,
                )
                link_targets.append((doc["id"], body, eid))
                continue

            if folder == "concepts":
                doc = ingest_text(
                    corpus_id, title=title, content=body, doc_type="concept",
                    source_kind="user_original",
                    tags=["gbrain", "concept"],
                    metadata=meta,
                    contributor_user_id=contributor_user_id,
                )
                concepts += 1
                link_targets.append((doc["id"], body, None))
                continue

            doc_type = "data" if folder == "sources" else "note"
            tags = ["gbrain"] + ([folder] if folder else [])
            meta["folder_path"] = folder
            doc = ingest_text(
                corpus_id, title=title, content=body, doc_type=doc_type,
                source_kind="user_original",
                tags=tags,
                metadata=meta,
                contributor_user_id=contributor_user_id,
            )
            sources += 1
            link_targets.append((doc["id"], body, None))
        except Exception as e:
            logger.warning("gbrain: failed to ingest %s: %s", rel, e)
            errors += 1

    links_resolved = _resolve_gbrain_links(
        link_targets, slug_to_eid, name_to_eid, get_conn
    )

    imported = entities_made + concepts + sources
    if imported > 0:
        try:
            index_corpus(corpus_id)
        except Exception as e:
            logger.warning("Index after gbrain import failed: %s", e)

    return {
        "total": total,
        "imported": imported,
        "entities": entities_made,
        "concepts": concepts,
        "sources": sources,
        "links_resolved": links_resolved,
        "skipped": skipped,
        "errors": errors,
        "source_kind": "user_original",
    }


def _resolve_gbrain_links(
    link_targets: list[tuple[str, str, str | None]],
    slug_to_eid: dict[str, str],
    name_to_eid: dict[str, str],
    get_conn,
) -> int:
    """Second pass: map gbrain cross-links in each doc body to entity ids.

    gbrain references other pages by filename slug — as a markdown link to a
    `*.md` path, or as a `[[wikilink]]`. Resolve both to entity ids and merge
    into the doc's metadata.mentioned_entity_ids (so referenced people/orgs
    light up on each other's entity pages). Idempotent per run.
    """
    if not link_targets:
        return 0
    conn = get_conn()
    total_links = 0
    for doc_id, body, own_eid in link_targets:
        found: list[str] = []

        def _add(eid: str | None) -> None:
            if eid and eid != own_eid and eid not in found:
                found.append(eid)

        for m in _MD_PAGE_LINK_PATTERN.finditer(body):
            target_slug = Path(m.group(1)).stem.lower()
            _add(slug_to_eid.get(target_slug))
        for m in _WIKILINK_PATTERN.finditer(body):
            target = m.group(1).strip()
            key = target.split("/")[-1].strip().lower()
            _add(slug_to_eid.get(key) or name_to_eid.get(key))

        if not found:
            continue
        row = conn.execute(
            "SELECT metadata_json FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        if not row:
            continue
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            meta = {}
        existing = meta.get("mentioned_entity_ids") or []
        merged = list(dict.fromkeys([*existing, *found]))
        if merged != existing:
            meta["mentioned_entity_ids"] = merged
            conn.execute(
                "UPDATE documents SET metadata_json=? WHERE id=?",
                (json.dumps(meta), doc_id),
            )
            total_links += len(set(found) - set(existing))
    conn.commit()
    return total_links


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
