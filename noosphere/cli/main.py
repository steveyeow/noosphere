"""Noosphere CLI — init, ingest, index, serve."""

import hashlib
import json
import os
from pathlib import Path

import click

from noosphere.core.config import HOST, PORT


def _writeback_to_vault(corpus_id: str, vault_dir: str | Path) -> dict:
    """Mirror synthesized entity/concept pages from a corpus into
    ``<vault>/__noosphere/`` on disk. Conflict-safe:

    - Tracks last-written hash per file in
      ``<vault>/__noosphere/.sync-state.json``.
    - Before overwriting, compares the current file's hash to the stored
      "last-written-by-us" hash. If they diverge, the user has edited the
      file locally — skip the overwrite and surface a count so the caller
      can warn.
    - After a successful write, records the new hash.

    The client stores the latest ``generated_at`` from the server so the
    next call can ask for an incremental diff via ``?since=...``. First
    call has no ``since`` and fetches everything.
    """
    from noosphere.core.writeback import compute_writeback

    vault = Path(vault_dir)
    out_root = vault / "__noosphere"
    out_root.mkdir(parents=True, exist_ok=True)
    state_path = out_root / ".sync-state.json"

    try:
        state = json.loads(state_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        state = {"last_generated_at": "", "hashes": {}}
    last_since = state.get("last_generated_at") or None

    payload = compute_writeback(corpus_id, since=last_since)
    written = 0
    skipped_conflict = 0

    for f in payload.get("files", []):
        rel_path = f["path"]
        target = out_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        new_hash = hashlib.sha256(f["content"].encode("utf-8")).hexdigest()

        if target.exists():
            current_hash = hashlib.sha256(
                target.read_text(encoding="utf-8", errors="replace").encode("utf-8")
            ).hexdigest()
            last_written = state["hashes"].get(rel_path)
            # If the file on disk doesn't match what we last wrote, the
            # user has edited it. Respect their edits.
            if last_written and current_hash != last_written:
                skipped_conflict += 1
                continue
            # Identical content — no-op.
            if current_hash == new_hash:
                state["hashes"][rel_path] = new_hash
                continue

        target.write_text(f["content"], encoding="utf-8")
        state["hashes"][rel_path] = new_hash
        written += 1

    state["last_generated_at"] = payload["generated_at"]
    state_path.write_text(json.dumps(state, indent=2))
    return {"written": written, "skipped_conflict": skipped_conflict}


@click.group(epilog="""
\b
Quickstart:
  noosphere connect-gbrain ~/brain --name "My Brain"   import a GBrain repo
  noosphere connect-obsidian ~/vault                    import an Obsidian vault
  noosphere serve --public-url https://your-host        serve it on the network
\b
Docs: https://github.com/steveyeow/noosphere
""")
def cli():
    """Noosphere — Turn any knowledge base into an agent-readable corpus.

    Coming from GBrain or Obsidian? `connect-gbrain` / `connect-obsidian`
    create a corpus and import in one step. See Quickstart below.
    """
    pass


@cli.command()
@click.argument("directory")
@click.option("--name", required=True, help="Corpus name")
@click.option("--author", default="", help="Author name")
@click.option("--description", default="", help="Corpus description")
@click.option("--provider", default="", help="Embedding provider: openai, gemini (auto-detect if empty)")
@click.option("--doc-type", default="doc", help="Document type label (e.g. doc, newsletter, podcast)")
@click.option("--chunk-strategy", default="paragraph", type=click.Choice(["paragraph", "recursive", "semantic"]),
              help="Chunking strategy: paragraph (default), recursive (transcripts), semantic (papers)")
def init(directory, name, author, description, provider, doc_type, chunk_strategy):
    """Initialize a new corpus from a directory of documents."""
    from noosphere.core.corpus import create_corpus
    from noosphere.core.ingest import ingest_directory
    from noosphere.core.indexer import index_corpus

    click.echo(f"Creating corpus: {name}")
    corpus = create_corpus(name, description=description, author_name=author)
    corpus_id = corpus["id"]
    click.echo(f"  ID: {corpus_id}")
    click.echo(f"  Slug: {corpus['slug']}")

    if chunk_strategy != "paragraph":
        from noosphere.core.corpus import update_corpus as uc
        uc(corpus_id, chunk_strategy=chunk_strategy)
        click.echo(f"  Chunk strategy: {chunk_strategy}")

    click.echo(f"\nIngesting documents from {directory}...")
    docs = ingest_directory(corpus_id, directory, doc_type=doc_type)
    click.echo(f"  Ingested {len(docs)} documents")

    click.echo("\nIndexing (chunking + embedding)...")

    def progress(stage, current, total):
        if stage == "chunking":
            click.echo(f"  Chunked into {current} segments")
        elif stage == "embedding":
            click.echo(f"  Embedding: {current}/{total}")
        elif stage == "done":
            click.echo(f"  Indexing complete: {current} chunks")

    result = index_corpus(corpus_id, provider=provider, on_progress=progress, chunk_strategy=chunk_strategy)
    click.echo("\nCorpus ready!")
    click.echo(f"  Chunks: {result['chunk_count']}")
    click.echo(f"  Model: {result['embedding_model']}")
    click.echo(f"\nServe with: noosphere serve --port {PORT}")


@cli.command()
@click.argument("directory")
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.option("--doc-type", default="doc", help="Document type")
def ingest(directory, corpus, doc_type):
    """Ingest additional documents into an existing corpus."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.ingest import ingest_directory

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    click.echo(f"Ingesting into: {c['name']} ({c['id']})")
    docs = ingest_directory(c["id"], directory, doc_type=doc_type)
    click.echo(f"  Ingested {len(docs)} documents")
    click.echo(f"\nRe-index with: noosphere index --corpus {c['id']}")


@cli.command()
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.option("--provider", default="", help="Embedding provider")
@click.option("--force", is_flag=True, help="Force re-index all documents (ignore content hashes)")
@click.option("--chunk-strategy", default="", type=click.Choice(["", "paragraph", "recursive", "semantic"]),
              help="Override chunking strategy for this index run")
def index(corpus, provider, force, chunk_strategy):
    """Re-index a corpus (incremental by default, --force for full re-index)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.indexer import index_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    mode = "full" if force else "incremental"
    click.echo(f"Indexing ({mode}): {c['name']} ({c['id']})")

    def progress(stage, current, total):
        if stage == "chunking":
            click.echo(f"  Chunked: {current} segments")
        elif stage == "embedding":
            click.echo(f"  Embedding: {current}/{total}")
        elif stage == "done":
            click.echo(f"  Done: {current} chunks embedded")

    result = index_corpus(c["id"], provider=provider, on_progress=progress,
                          force=force, chunk_strategy=chunk_strategy)
    click.echo(f"\nIndexing complete: {result['chunk_count']} total chunks")
    if result.get("skipped"):
        click.echo(f"  Skipped (unchanged): {result['skipped']}")
    if result.get("embedded"):
        click.echo(f"  Newly embedded: {result['embedded']}")


@cli.command("reindex-all")
@click.option("--provider", default="", help="Embedding provider (e.g. zhipu, openai, gemini). Empty = auto.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def reindex_all_cmd(provider, yes):
    """Force re-embed every corpus — use after switching embedding providers.

    Embeddings from different providers have different dims, so the old
    chunks can't be queried with the new embedder. This drops all chunk
    vectors and re-embeds from the stored documents.
    """
    from noosphere.core.corpus import list_corpora
    from noosphere.core.indexer import index_corpus

    corpora = list_corpora(include_private=True)
    if not corpora:
        click.echo("No corpora found.")
        return
    click.echo(f"Will re-index {len(corpora)} corpora with provider='{provider or 'auto'}':")
    for c in corpora:
        click.echo(f"  - {c['name']} ({c['id']}) — currently {c.get('embedding_model') or 'unindexed'}")
    if not yes and not click.confirm("Proceed?", default=False):
        click.echo("Aborted.")
        return
    for c in corpora:
        click.echo(f"\n→ {c['name']} ({c['id']})")
        try:
            result = index_corpus(c["id"], provider=provider, force=True)
            click.echo(f"   {result['chunk_count']} chunks embedded")
        except Exception as e:
            click.echo(f"   FAILED: {e}", err=True)


@cli.command()
@click.option("--port", default=PORT, help="Server port")
@click.option("--host", default=HOST, help="Server host")
@click.option("--no-registry", is_flag=True, help="Don't register with the discovery registry")
@click.option("--registry", "registry_url", default="", help="Custom registry URL (overrides NOOSPHERE_REGISTRY)")
@click.option("--public-url", default="", help="Public URL for this node (for registry registration)")
def serve(port, host, no_registry, registry_url, public_url):
    """Serve corpora via REST API, MCP, and web frontend."""
    import uvicorn
    from noosphere.core.config import NOOSPHERE_REGISTRY

    click.echo(f"Starting Noosphere server on {host}:{port}")
    click.echo(f"  REST API:  http://{host}:{port}/api/v1/corpora")
    click.echo(f"  Web UI:    http://{host}:{port}/")
    click.echo(f"  MCP:       http://{host}:{port}/mcp")
    click.echo(f"  Manifest:  http://{host}:{port}/.well-known/noosphere.json")

    if no_registry:
        # Lifespan reads NOOSPHERE_REGISTRY too — clear it so the FastAPI
        # startup hook also skips, otherwise --no-registry would only mute
        # the CLI but lifespan would still POST.
        os.environ["NOOSPHERE_REGISTRY"] = "none"
        click.echo("  Registry:  disabled (--no-registry)")
    else:
        registry = registry_url or NOOSPHERE_REGISTRY
        if registry:
            endpoint = public_url or f"http://{host}:{port}"
            from noosphere.core.registry import (
                is_local_endpoint, register_with_registry, set_node_endpoint,
            )
            if is_local_endpoint(endpoint):
                click.echo(f"  Registry:  {registry} (not registering — endpoint is localhost; pass --public-url to join the network)")
            else:
                click.echo(f"  Registry:  {registry}")
                # Make APP_URL match what we're advertising so the FastAPI
                # lifespan hook can resync on subsequent restarts even if
                # the CLI isn't the entrypoint next time (Docker, systemd).
                os.environ.setdefault("APP_URL", endpoint)
                set_node_endpoint(endpoint)
                ok = register_with_registry(endpoint, registry_url=registry)
                if ok:
                    click.echo("  Registered with the Noosphere registry")
                else:
                    click.echo("  Registry registration failed (may be unreachable — see logs)")

    uvicorn.run("noosphere.api.main:app", host=host, port=port, reload=False)


@cli.command("list")
def list_cmd():
    """List all corpora."""
    from noosphere.core.corpus import list_corpora

    corpora = list_corpora(include_private=True)
    if not corpora:
        click.echo("No corpora found. Create one with: noosphere init <directory> --name <name>")
        return

    for c in corpora:
        status_icon = {"ready": "+", "indexing": "~", "draft": "-", "error": "!"}.get(c["status"], "?")
        click.echo(f"  [{status_icon}] {c['name']} ({c['slug']}) — {c['document_count']} docs, {c['chunk_count']} chunks")


@cli.command()
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.argument("query")
def search(corpus, query):
    """Search a corpus from the command line."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.retrieval import search_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    results = search_corpus(c["id"], query)
    if not results["results"]:
        click.echo("No results found.")
        return

    for i, r in enumerate(results["results"], 1):
        cite = r.get("citation", {})
        click.echo(f"\n--- Result {i} (score: {r['score']}) ---")
        if cite.get("document_title"):
            click.echo(f"Source: {cite['document_title']}")
        if cite.get("date"):
            click.echo(f"Date: {cite['date']}")
        click.echo(f"\n{r['text'][:500]}")

    click.echo(f"\n({results['usage']['latency_ms']}ms, {results['usage']['chunks_searched']} chunks searched)")


@cli.command()
@click.argument("directory")
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.option("--doc-type", default="doc", help="Document type for new files")
@click.option("--prune", is_flag=True, help="Remove documents whose source files no longer exist")
@click.option("--provider", default="", help="Embedding provider")
@click.option("--obsidian", "obsidian_mode", is_flag=True,
              help="Treat the directory as an Obsidian vault (parse wikilinks, tags, "
                   "frontmatter; skip .obsidian/ and .trash/; source_kind=user_original)")
@click.option("--watch", is_flag=True,
              help="Keep running and re-sync whenever files change. "
                   "Uses a polling loop (no watchdog dependency required).")
@click.option("--interval", default=2.0, help="Watch polling interval in seconds (default: 2)")
@click.option("--writeback/--no-writeback", default=True,
              help="Mirror Noosphere-synthesized entity and concept pages into "
                   "<vault>/__noosphere/ after each sync (default: on). "
                   "Local edits to these files are preserved — the CLI detects "
                   "hash drift and skips overwriting.")
def sync(directory, corpus, doc_type, prune, provider, obsidian_mode, watch, interval, writeback):
    """Sync a directory to an existing corpus (add new, update changed, optionally prune deleted).

    Karpathy-style setup (local vault on disk, LLM-maintained wiki):

        noosphere sync ~/my-vault --corpus my-kb --obsidian --watch

    The vault stays on your disk; Noosphere mirrors it into the corpus and
    keeps the index fresh as you edit in Obsidian. By default, Noosphere
    writes synthesized entity and concept pages back to
    <vault>/__noosphere/ so enrichments live alongside your sources —
    pass --no-writeback to disable.
    """
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.ingest import sync_directory
    from noosphere.core.indexer import index_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    fmt = "obsidian" if obsidian_mode else "generic"

    def _run_once():
        result = sync_directory(c["id"], directory, doc_type=doc_type, prune=prune, format=fmt)
        click.echo(f"  {result['new']} new, {result['updated']} updated, "
                   f"{result['pruned']} pruned, {result['unchanged']} unchanged")

        if result["new"] or result["updated"]:
            click.echo("  Indexing changed documents...")

            def progress(stage, current, total):
                if stage == "embedding" and total and current % max(1, total // 4) == 0:
                    click.echo(f"    Embedding: {current}/{total}")
                elif stage == "done":
                    click.echo(f"    Indexed {current} chunks")

            idx_result = index_corpus(c["id"], provider=provider, on_progress=progress)
            if idx_result.get("skipped"):
                click.echo(f"  Skipped (unchanged): {idx_result['skipped']}")

        if writeback:
            try:
                wb = _writeback_to_vault(c["id"], directory)
                if wb["written"] or wb["skipped_conflict"]:
                    click.echo(f"  Writeback: {wb['written']} file(s) written"
                               f"{', '+str(wb['skipped_conflict'])+' skipped (local edits preserved)' if wb['skipped_conflict'] else ''}")
            except Exception as e:
                click.echo(f"  Writeback error: {e}", err=True)
        return result

    mode_label = "Obsidian vault" if obsidian_mode else "directory"
    click.echo(f"Syncing {mode_label} {directory} → {c['name']} ({c['id']})")
    _run_once()

    if not watch:
        return

    # Polling watch mode — rescan the tree every `interval` seconds and detect
    # changes by the max mtime across all tracked files. This is cheap for
    # typical vaults (<5k files) and avoids the watchdog dependency.
    import os
    import time
    from pathlib import Path

    directory_path = Path(directory)
    if obsidian_mode:
        def list_tracked():
            return [
                f for f in directory_path.rglob("*.md")
                if f.is_file()
                and not any(p.startswith(".") for p in f.relative_to(directory_path).parts)
            ]
    else:
        from noosphere.core.ingest import SUPPORTED_FILE_EXTENSIONS
        def list_tracked():
            return [
                f for f in directory_path.rglob("*")
                if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
            ]

    def fingerprint():
        fps = []
        for f in list_tracked():
            try:
                st = f.stat()
                fps.append((str(f), st.st_mtime, st.st_size))
            except OSError:
                continue
        return frozenset(fps)

    last_fp = fingerprint()
    click.echo(f"\nWatching {directory} for changes (polling every {interval}s, Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(interval)
            fp = fingerprint()
            if fp != last_fp:
                last_fp = fp
                click.echo(f"\n[{time.strftime('%H:%M:%S')}] Change detected — resyncing")
                try:
                    _run_once()
                except Exception as e:
                    click.echo(f"  Sync error: {e}", err=True)
    except KeyboardInterrupt:
        click.echo("\nWatch stopped.")


@cli.command("connect-obsidian")
@click.argument("vault_path")
@click.option("--name", default="", help="Name for the new corpus (default: vault folder name)")
@click.option("--access-level", default="private",
              type=click.Choice(["public", "private", "token", "paid"]),
              help="Access level for the new corpus (default: private)")
@click.option("--provider", default="", help="Embedding provider")
@click.option("--no-writeback", is_flag=True, help="Disable writeback of synthesized pages back to the vault")
@click.option("--watch", is_flag=True, help="Keep running and re-sync on every file change")
def connect_obsidian_cmd(vault_path, name, access_level, provider, no_writeback, watch):
    """Create a new corpus and sync an Obsidian vault into it in one step.

    Shortcut for the usual flow:
      1. noosphere init <vault> --name "X"    — create corpus
      2. noosphere sync <vault> --corpus X --obsidian --watch
           --writeback/--no-writeback

    After the initial sync, the printed corpus ID can be pasted into the
    Obsidian plugin's "Corpus ID" setting if you want to continue via the
    in-editor UI instead of the CLI.
    """
    from pathlib import Path
    from noosphere.core.corpus import create_corpus
    from noosphere.core.ingest import sync_directory
    from noosphere.core.indexer import index_corpus
    from noosphere.core.registry import resync_registry

    vault = Path(vault_path).expanduser()
    if not vault.is_dir():
        click.echo(f"Vault path is not a directory: {vault}", err=True)
        raise SystemExit(1)

    corpus_name = name.strip() or vault.name or "My Obsidian Vault"
    click.echo(f"Creating corpus '{corpus_name}' (access: {access_level})...")
    corpus = create_corpus(
        corpus_name,
        description=f"Synced from Obsidian vault at {vault}",
        access_level=access_level,
    )
    cid = corpus["id"]
    click.echo(f"  ID: {cid}")
    click.echo(f"  Slug: {corpus['slug']}")

    click.echo(f"\nSyncing vault {vault} → {corpus_name}...")
    result = sync_directory(cid, str(vault), format="obsidian", prune=False)
    click.echo(f"  {result['new']} new, {result['updated']} updated, "
               f"{result['unchanged']} unchanged")

    if result["new"] or result["updated"]:
        click.echo("  Indexing...")
        index_result = index_corpus(cid, provider=provider)
        click.echo(f"  {index_result['chunk_count']} chunks indexed")

    if not no_writeback:
        try:
            wb = _writeback_to_vault(cid, str(vault))
            if wb["written"] or wb["skipped_conflict"]:
                click.echo(f"  Writeback: {wb['written']} file(s) written to __noosphere/"
                           + (f", {wb['skipped_conflict']} skipped (local edits preserved)" if wb["skipped_conflict"] else ""))
        except Exception as e:
            click.echo(f"  Writeback error: {e}", err=True)

    # Non-private corpora should be visible in the network immediately.
    if access_level != "private":
        resync_registry()

    click.echo(f"\nCorpus ready: {cid}")
    if watch:
        click.echo(f"\nEntering watch mode. Ctrl+C to stop.")
        import time
        from noosphere.core.ingest import SUPPORTED_FILE_EXTENSIONS as _EXT
        def list_md():
            return [
                f for f in vault.rglob("*.md")
                if f.is_file()
                and not any(p.startswith(".") for p in f.relative_to(vault).parts)
                and not any(p == "__noosphere" for p in f.relative_to(vault).parts)
            ]
        def fp():
            return frozenset(
                (str(f), f.stat().st_mtime, f.stat().st_size) for f in list_md()
            )
        last = fp()
        try:
            while True:
                time.sleep(2.0)
                cur = fp()
                if cur != last:
                    last = cur
                    click.echo(f"\n[{time.strftime('%H:%M:%S')}] change detected, resyncing")
                    try:
                        r = sync_directory(cid, str(vault), format="obsidian", prune=False)
                        click.echo(f"  {r['new']} new, {r['updated']} upd, {r['unchanged']} same")
                        if r["new"] or r["updated"]:
                            index_corpus(cid, provider=provider)
                        if not no_writeback:
                            _writeback_to_vault(cid, str(vault))
                    except Exception as e:
                        click.echo(f"  sync error: {e}", err=True)
        except KeyboardInterrupt:
            click.echo("\nWatch stopped.")
    else:
        click.echo(f"\nTo keep syncing as you edit, run:")
        click.echo(f"  noosphere sync {vault} --corpus {cid} --obsidian --watch")


@cli.command("import-gbrain")
@click.argument("repo_path")
@click.option("--corpus", required=True, help="Corpus ID or slug to import into")
@click.option("--provider", default="", help="Embedding provider (re-index after import)")
def import_gbrain_cmd(repo_path, corpus, provider):
    """Import a GBrain repo directory into an existing corpus.

    Maps gbrain's structure into Noosphere at full fidelity:
      people/ + companies/  → entities (compiled truth = entity description)
      concepts/             → Wiki concept pages
      meetings/ ideas/ ...  → source documents
    Cross-page slug links resolve to entity references.
    """
    from pathlib import Path
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.importers import import_gbrain_repo
    from noosphere.core.indexer import index_corpus

    repo = Path(repo_path).expanduser()
    if not repo.is_dir():
        click.echo(f"Not a directory: {repo}", err=True)
        raise SystemExit(1)
    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    click.echo(f"Importing GBrain repo {repo} → {c['name']} ({c['id']})...")
    r = import_gbrain_repo(c["id"], str(repo))
    click.echo(f"  {r['entities']} entities, {r['concepts']} concept pages, "
               f"{r['sources']} sources, {r['links_resolved']} cross-links resolved")
    if r["skipped"] or r["errors"]:
        click.echo(f"  {r['skipped']} skipped, {r['errors']} errors")
    if provider:
        click.echo("  Re-indexing with provider...")
        index_corpus(c["id"], provider=provider)
    click.echo(f"\nDone: {c['id']}")


@cli.command("connect-gbrain")
@click.argument("repo_path")
@click.option("--name", default="", help="Name for the new corpus (default: repo folder name)")
@click.option("--access-level", default="private",
              type=click.Choice(["public", "private", "token", "paid"]),
              help="Access level for the new corpus (default: private)")
@click.option("--provider", default="", help="Embedding provider")
def connect_gbrain_cmd(repo_path, name, access_level, provider):
    """Create a new corpus and import a GBrain repo into it in one step.

    The fastest path for a gbrain user onto the Noosphere network:

        noosphere connect-gbrain ~/brain --name "My Brain" --access-level public

    people/ and companies/ become entity pages whose compiled truth is the
    entity description; concepts/ become Wiki pages; the rest become sources.
    A non-private corpus is published to the network immediately.
    """
    from pathlib import Path
    from noosphere.core.corpus import create_corpus
    from noosphere.core.importers import import_gbrain_repo
    from noosphere.core.indexer import index_corpus
    from noosphere.core.registry import resync_registry

    repo = Path(repo_path).expanduser()
    if not repo.is_dir():
        click.echo(f"Repo path is not a directory: {repo}", err=True)
        raise SystemExit(1)

    corpus_name = name.strip() or repo.name or "My GBrain"
    click.echo(f"Creating corpus '{corpus_name}' (access: {access_level})...")
    corpus = create_corpus(
        corpus_name,
        description=f"Imported from GBrain repo at {repo}",
        access_level=access_level,
    )
    cid = corpus["id"]
    click.echo(f"  ID: {cid}")
    click.echo(f"  Slug: {corpus['slug']}")

    click.echo(f"\nImporting GBrain repo {repo}...")
    r = import_gbrain_repo(cid, str(repo))
    click.echo(f"  {r['entities']} entities, {r['concepts']} concept pages, "
               f"{r['sources']} sources, {r['links_resolved']} cross-links resolved")
    if r["skipped"] or r["errors"]:
        click.echo(f"  {r['skipped']} skipped, {r['errors']} errors")
    if provider:
        click.echo("  Re-indexing with provider...")
        index_corpus(cid, provider=provider)

    if access_level != "private":
        resync_registry()
        click.echo("  Published to the network.")

    click.echo(f"\nCorpus ready: {cid}")
    if access_level != "private":
        click.echo("\nTo serve it for agents on the network:")
        click.echo("  noosphere serve --public-url https://your-host")
    click.echo("\nTo re-import after your brain changes:")
    click.echo(f"  noosphere import-gbrain {repo} --corpus {cid}")


@cli.command("ingest-feed")
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.argument("feed_url")
@click.option("--max-items", default=25, help="Max feed entries to process")
def ingest_feed_cmd(corpus, feed_url, max_items):
    """Ingest new items from an RSS or Atom URL (recurring inflow)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.knowledge_growth import ingest_rss_feed

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)
    click.echo(f"Ingesting feed into {c['name']} ({c['id']})...")
    result = ingest_rss_feed(c["id"], feed_url.strip(), max_items=max_items)
    click.echo(f"  Fetched {result['fetched']} entries, ingested {result['ingested']}, skipped {result['skipped']}")
    if result.get("index") and "chunk_count" in result["index"]:
        click.echo(f"  Chunks: {result['index']['chunk_count']}")


@cli.command("ingest-urls")
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.argument("urls", nargs=-1, required=True)
@click.option("--doc-type", default="blog", help="Document type label")
def ingest_urls_cmd(corpus, urls, doc_type):
    """Ingest multiple URLs in one shot (paste many links)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.knowledge_growth import ingest_urls_bulk

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)
    if len(urls) > 40:
        click.echo("Maximum 40 URLs", err=True)
        raise SystemExit(1)
    result = ingest_urls_bulk(c["id"], list(urls), doc_type=doc_type)
    click.echo(f"Ingested {result['ingested']}, failed {result['failed']}")
    for err in result.get("errors", [])[:5]:
        click.echo(f"  ! {err.get('url')}: {err.get('error')}")


@cli.command("compile")
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.argument("topic")
@click.option("--top-k", default=10, help="Retrieval breadth")
def compile_cmd(corpus, topic, top_k):
    """LLM-compile a concept note from retrieved passages (requires chat API keys)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.knowledge_growth import compile_concept_note

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)
    doc = compile_concept_note(c["id"], topic, top_k=top_k)
    click.echo(f"Created concept document: {doc['title']} ({doc['id']})")


@cli.command("recompile-dirty-concepts")
@click.option("--corpus", default="", help="Corpus ID or slug (omit to scan ALL corpora)")
@click.option("--force", is_flag=True, help="Recompile every concept (ignore threshold)")
def recompile_dirty_concepts_cmd(corpus, force):
    """Re-synthesize living-concept notes whose timelines have accumulated new sources."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.knowledge_growth import recompile_dirty_concepts

    corpus_id: str | None = None
    if corpus:
        c = get_corpus(corpus) or get_corpus_by_slug(corpus)
        if not c:
            click.echo(f"Corpus not found: {corpus}", err=True)
            raise SystemExit(1)
        corpus_id = c["id"]

    result = recompile_dirty_concepts(corpus_id, force=force)
    click.echo(
        f"Scanned {result['total']} concept docs · "
        f"recompiled {len(result['recompiled'])}, skipped {len(result['skipped'])}, "
        f"errors {len(result['errors'])}"
    )
    for err in result["errors"][:5]:
        click.echo(f"  ! {err['concept_id']}: {err['error']}")


@cli.command("health-knowledge")
@click.option("--corpus", required=True, help="Corpus ID or slug")
def health_knowledge_cmd(corpus):
    """Show corpus knowledge-health report (coverage, staleness)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.knowledge_growth import corpus_knowledge_health

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)
    r = corpus_knowledge_health(c["id"])
    click.echo(f"Documents: {r['document_count']}")
    click.echo(f"Without chunks: {r['documents_without_chunks_count']}")
    click.echo(f"Capture docs: {r['capture_documents']} | Concept docs: {r['concept_documents']}")
    click.echo(f"Suspected empty markdown links: {r['suspected_empty_markdown_links']}")
    click.echo(f"Older than {r['stale_threshold_days']}d: {r['documents_older_than_threshold_count']}")


@cli.command()
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.option("--output", default="", help="Output file path (default: <slug>.zip)")
def export(corpus, output):
    """Export a corpus as a portable zip package (SPEC-compliant format)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.export import export_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    out_path = output or f"{c['slug']}.zip"
    buf = export_corpus(c["id"])
    with open(out_path, "wb") as f:
        f.write(buf.read())

    click.echo(f"Exported to {out_path} (SPEC-compliant format)")


def main():
    cli()


if __name__ == "__main__":
    main()
