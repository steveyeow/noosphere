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
def init(directory, name, author, description, provider, doc_type):
    """Initialize a new corpus from a directory of documents."""
    from noosphere.core.corpus import create_corpus
    from noosphere.core.ingest import ingest_directory
    from noosphere.core.indexer import index_corpus

    click.echo(f"Creating corpus: {name}")
    corpus = create_corpus(name, description=description, author_name=author)
    corpus_id = corpus["id"]
    click.echo(f"  ID: {corpus_id}")
    click.echo(f"  Slug: {corpus['slug']}")

    click.echo(f"\nIngesting documents from {directory}...")
    docs = ingest_directory(corpus_id, directory, doc_type=doc_type)
    click.echo(f"  Ingested {len(docs)} documents")

    click.echo(f"\nIndexing (chunking + embedding)...")

    def progress(stage, current, total):
        if stage == "chunking":
            click.echo(f"  Chunked into {current} segments")
        elif stage == "embedding":
            click.echo(f"  Embedding: {current}/{total}")
        elif stage == "done":
            click.echo(f"  Indexing complete: {current} chunks")

    result = index_corpus(corpus_id, provider=provider, on_progress=progress)
    click.echo(f"\nCorpus ready!")
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
def index(corpus, provider):
    """Re-index a corpus (re-chunk and re-embed all documents)."""
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.indexer import index_corpus

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    click.echo(f"Indexing: {c['name']} ({c['id']})")

    def progress(stage, current, total):
        if stage == "embedding":
            click.echo(f"  Embedding: {current}/{total}")
        elif stage == "done":
            click.echo(f"  Done: {current} chunks")

    result = index_corpus(c["id"], provider=provider, on_progress=progress)
    click.echo(f"\nIndexing complete: {result['chunk_count']} chunks")


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
                click.echo("  Registered with discovery registry")
            else:
                click.echo("  Registry registration skipped (registry may be unreachable)")
    else:
        click.echo("  Registry:  disabled (--no-registry)")

    uvicorn.run("noosphere.api.main:app", host=host, port=port, reload=False)


@cli.command("list")
def list_cmd():
    """List all corpora."""
    from noosphere.core.corpus import list_corpora

    corpora = list_corpora()
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
@click.option("--corpus", required=True, help="Corpus ID or slug")
@click.option("--output", default="", help="Output file path (default: <slug>.zip)")
def export(corpus, output):
    """Export a corpus as a portable zip package."""
    import json
    import zipfile
    from noosphere.core.corpus import get_corpus, get_corpus_by_slug
    from noosphere.core.ingest import get_documents

    c = get_corpus(corpus) or get_corpus_by_slug(corpus)
    if not c:
        click.echo(f"Corpus not found: {corpus}", err=True)
        raise SystemExit(1)

    out_path = output or f"{c['slug']}.zip"
    docs = get_documents(c["id"])

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("noosphere.json", json.dumps(c, indent=2, ensure_ascii=False))
        for doc in docs:
            filename = f"documents/{doc['id']}.md"
            content = doc.get("content", "")
            title = doc.get("title", "")
            header = f"---\ntitle: {title}\ndate: {doc.get('date', '')}\n---\n\n"
            zf.writestr(filename, header + content)

    click.echo(f"Exported {len(docs)} documents to {out_path}")


def main():
    cli()


if __name__ == "__main__":
    main()
