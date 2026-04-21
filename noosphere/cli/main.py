"""Noosphere CLI — init, ingest, index, serve."""

import click

from noosphere.core.config import HOST, PORT


@click.group()
def cli():
    """Noosphere — Turn any knowledge base into an agent-readable corpus."""
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

    if not no_registry:
        registry = registry_url or NOOSPHERE_REGISTRY
        if registry:
            endpoint = public_url or f"http://{host}:{port}"
            click.echo(f"  Registry:  {registry}")
            from noosphere.core.registry import register_with_registry
            ok = register_with_registry(endpoint, registry_url=registry)
            if ok:
                click.echo("  Registered with the Noosphere registry")
            else:
                click.echo("  Registry registration skipped (may be unreachable)")
    else:
        click.echo("  Registry:  disabled (--no-registry)")

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
def sync(directory, corpus, doc_type, prune, provider):
    """Sync a directory to an existing corpus (add new, update changed, optionally prune deleted)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.ingest import sync_directory
    from noosphere.core.indexer import index_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    click.echo(f"Syncing {directory} → {c['name']} ({c['id']})")
    result = sync_directory(c["id"], directory, doc_type=doc_type, prune=prune)
    click.echo(f"  {result['new']} new, {result['updated']} updated, "
               f"{result['pruned']} pruned, {result['unchanged']} unchanged")

    if result["new"] or result["updated"]:
        click.echo("\nIndexing changed documents...")

        def progress(stage, current, total):
            if stage == "embedding":
                click.echo(f"  Embedding: {current}/{total}")
            elif stage == "done":
                click.echo(f"  Done: {current} chunks embedded")

        idx_result = index_corpus(c["id"], provider=provider, on_progress=progress)
        click.echo(f"  Total chunks: {idx_result['chunk_count']}")
        if idx_result.get("skipped"):
            click.echo(f"  Skipped (unchanged): {idx_result['skipped']}")
    else:
        click.echo("  Nothing to re-index.")


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
