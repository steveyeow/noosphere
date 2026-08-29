#!/usr/bin/env python3
"""IndexNow helper: mint a key and submit URLs to Bing/Yandex/Seznam/Naver.

Why this exists: Google discovers URLs on its own crawl schedule, but Bing's
index also powers ChatGPT search, Microsoft Copilot, DuckDuckGo, Yahoo and
Ecosia — and Bing accepts push notification via IndexNow with NO webmaster
account. The key file served from the site's public dir proves ownership;
the key is public by design, not a secret.

Usage:
    # one-time: mint a key and write <key>.txt into the public dir
    python3 indexnow.py gen-key --public-dir public

    # submit every URL in the sitemap (follows one level of sitemap index)
    python3 indexnow.py submit --site https://example.com --public-dir public

    # submit specific URLs (new/updated/removed pages)
    python3 indexnow.py submit --site https://example.com --key <key> URL [URL...]

Key discovery order for submit: --key flag, then a [0-9a-f]{32}.txt file in
--public-dir. Re-running submit with unchanged URLs is harmless (engines
treat submissions as hints; duplicates are ignored). Only submit URLs that
are actually live — staging the script pre-launch is fine, firing it isn't.

Stdlib only; copy this file into the project so publish hooks and CI own it.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.indexnow.org/indexnow"  # fans out to all engines
BATCH_LIMIT = 10_000  # protocol max per POST
KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "indexnow-submit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def find_key(public_dir: Path) -> str | None:
    """Locate an existing IndexNow key file (<32-hex>.txt) in the public dir."""
    for path in sorted(public_dir.glob("*.txt")):
        if KEY_RE.match(path.stem) and path.read_text(encoding="utf-8").strip() == path.stem:
            return path.stem
    return None


def gen_key(public_dir: Path) -> int:
    public_dir.mkdir(parents=True, exist_ok=True)
    existing = find_key(public_dir)
    if existing:
        print(f"key already present: {public_dir / (existing + '.txt')}")
        return 0
    key = secrets.token_hex(16)
    key_file = public_dir / f"{key}.txt"
    key_file.write_text(key, encoding="utf-8")
    print(f"minted IndexNow key: {key}")
    print(f"wrote proof file:    {key_file}")
    print("deploy it, then submit with:")
    print(f"  python3 {Path(__file__).name} submit --site https://<host> --key {key}")
    return 0


def collect_sitemap_urls(site: str) -> list[str]:
    """All <loc> page URLs, following one level of sitemap-index children."""
    root = _fetch(f"{site}/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", root)
    if "<sitemapindex" in root:
        urls: list[str] = []
        for child in locs:
            try:
                urls.extend(re.findall(r"<loc>([^<]+)</loc>", _fetch(child)))
            except Exception as exc:  # noqa: BLE001
                print(f"  ! child sitemap {child}: {exc}", file=sys.stderr)
        return urls
    return locs


def submit(site: str, key: str, urls: list[str]) -> int:
    host = site.removeprefix("https://").removeprefix("http://").strip("/")
    for start in range(0, len(urls), BATCH_LIMIT):
        batch = urls[start : start + BATCH_LIMIT]
        body = json.dumps(
            {
                "host": host,
                "key": key,
                "keyLocation": f"{site.rstrip('/')}/{key}.txt",
                "urlList": batch,
            }
        ).encode()
        req = urllib.request.Request(
            ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"submitted {len(batch)} URLs -> HTTP {resp.status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("gen-key", help="mint a key + write <key>.txt proof file")
    p_gen.add_argument("--public-dir", type=Path, required=True,
                       help="static/public dir served at the site root")

    p_sub = sub.add_parser("submit", help="submit URLs (default: whole sitemap)")
    p_sub.add_argument("--site", required=True, help="canonical origin, e.g. https://example.com")
    p_sub.add_argument("--key", help="IndexNow key (else discovered from --public-dir)")
    p_sub.add_argument("--public-dir", type=Path, help="dir containing <key>.txt")
    p_sub.add_argument("urls", nargs="*", help="specific URLs; empty = entire sitemap")

    args = parser.parse_args()

    if args.cmd == "gen-key":
        return gen_key(args.public_dir)

    key = args.key or (find_key(args.public_dir) if args.public_dir else None)
    if not key or not KEY_RE.match(key):
        print("ERROR: no IndexNow key — pass --key or --public-dir containing <key>.txt "
              "(mint one with the gen-key subcommand)", file=sys.stderr)
        return 1
    urls = args.urls or collect_sitemap_urls(args.site.rstrip("/"))
    if not urls:
        print("no URLs to submit (empty sitemap?)", file=sys.stderr)
        return 1
    print(f"submitting {len(urls)} URLs for {args.site} ...")
    return submit(args.site.rstrip("/"), key, urls)


if __name__ == "__main__":
    sys.exit(main())
