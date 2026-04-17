"""Terminal command handler — parses user input and routes to appropriate action."""

import re
from noosphere.core.corpus import list_corpora, create_corpus
from noosphere.core.ingest import ingest_url, ingest_text
from noosphere.core.indexer import index_corpus


def handle_terminal_input(text: str, context: dict | None = None) -> dict:
    """Process terminal input and return structured response.

    Home terminal is chat-first (you're talking to Noos). Routing:
      - URL → ingest into a corpus (with inline corpus picker)
      - /command → slash-command handler
      - anything else → chat with Noos across all your corpora

    State tracks mid-flow interactions (e.g. waiting for corpus choice).
    """
    text = text.strip()
    ctx = context or {}
    state = ctx.get("state", "idle")

    if state == "pick_corpus":
        return _handle_corpus_pick(text, ctx)

    if _is_url(text):
        return _handle_url(text)

    if text.startswith("/"):
        return _handle_slash(text)

    # Default: chat with Noos.
    return _handle_question(text)


def _is_url(text: str) -> bool:
    return bool(re.match(r'https?://', text.strip()))


def _resolve_corpus_or_prompt(*, url: str = "", write_content: str = "", write_title: str = "") -> dict:
    """Pick a corpus automatically or prompt the user to choose.

    - 0 corpora → create "My Knowledge" and use it
    - 1 corpus → use it directly
    - 2+ corpora → show numbered list + "New corpus" option, enter pick_corpus state
    """
    corpora = list_corpora(include_private=True)

    if len(corpora) == 0:
        corpus = create_corpus("My Knowledge", access_level="public")
        return {"corpus": corpus, "prompt": None}

    if len(corpora) == 1:
        return {"corpus": corpora[0], "prompt": None}

    lines = [{"type": "resp", "text": "Which corpus should this go into?"}]
    ids = []
    for i, c in enumerate(corpora, 1):
        lines.append({
            "type": "option",
            "text": f"[{i}] {c['name']} ({c['document_count']} documents)",
            "value": str(i),
        })
        ids.append(c["id"])
    lines.append({
        "type": "option",
        "text": f"[{len(corpora) + 1}] + Create new corpus",
        "value": str(len(corpora) + 1),
    })

    return {
        "corpus": None,
        "prompt": {
            "lines": lines,
            "context": {
                "state": "pick_corpus",
                "corpora_ids": ids,
                "url": url,
                "write_content": write_content,
                "write_title": write_title,
            },
        },
    }


def _handle_url(url: str) -> dict:
    lines = [{"type": "resp", "text": f"Fetching {url}..."}]

    result = _resolve_corpus_or_prompt(url=url)
    if result["prompt"]:
        fetch_lines = list(lines)
        prompt = result["prompt"]
        prompt["lines"] = fetch_lines + prompt["lines"]
        return prompt

    corpus = result["corpus"]
    corpus_name = corpus["name"]
    cid = corpus["id"]

    try:
        doc = ingest_url(cid, url)
        lines.append({"type": "resp", "text": f'✓ Extracted: "{doc["title"]}" · {doc["word_count"]} words'})
        lines.append({"type": "resp", "text": f"Indexing into {corpus_name}..."})
        idx = index_corpus(cid)
        lines.append({"type": "resp", "text": f"✓ Indexed: {idx['chunk_count']} chunks"})
        lines.append({"type": "card", "label": "Source Added", "status": "READY",
                       "detail": f'{doc["title"]} · {corpus_name}',
                       "val": f'{idx["chunk_count"]} chunks · {doc["word_count"]} words',
                       "corpus_id": cid})
        lines.append({"type": "resp", "text": "Agents can now cite this content."})
    except Exception as e:
        lines.append({"type": "resp", "text": f"✗ Failed: {str(e)[:120]}"})

    return {"lines": lines, "context": {"state": "idle"}}


def _handle_corpus_pick(text: str, ctx: dict) -> dict:
    url = ctx.get("url", "")
    corpora_ids = ctx.get("corpora_ids", [])
    write_content = ctx.get("write_content", "")
    write_title = ctx.get("write_title", "")

    try:
        pick = int(text.strip())
    except ValueError:
        return {"lines": [{"type": "resp", "text": "Please enter a number."}], "context": ctx}

    if pick == len(corpora_ids) + 1:
        corpus = create_corpus("My Knowledge", access_level="public")
        cid = corpus["id"]
        corpus_name = "My Knowledge"
    elif 1 <= pick <= len(corpora_ids):
        cid = corpora_ids[pick - 1]
        from noosphere.core.corpus import get_corpus
        c = get_corpus(cid)
        corpus_name = c["name"] if c else "Unknown"
    else:
        return {"lines": [{"type": "resp", "text": "Invalid choice."}], "context": ctx}

    lines = []
    try:
        if url:
            doc = ingest_url(cid, url)
            lines.append({"type": "resp", "text": f'✓ Extracted: "{doc["title"]}" · {doc["word_count"]} words'})
        elif write_content:
            doc = ingest_text(cid, title=write_title or "Untitled", content=write_content)
            lines.append({"type": "resp", "text": f'✓ Saved: "{doc["title"]}"'})

        lines.append({"type": "resp", "text": f"Indexing into {corpus_name}..."})
        result = index_corpus(cid)
        lines.append({"type": "resp", "text": f"✓ {result['chunk_count']} chunks indexed"})
        lines.append({"type": "card", "label": "Source Added", "status": "READY",
                       "detail": f'{corpus_name} · {result["chunk_count"]} chunks',
                       "corpus_id": cid})
        lines.append({"type": "resp", "text": "Agents can now cite this content."})
    except Exception as e:
        lines.append({"type": "resp", "text": f"✗ Failed: {str(e)[:100]}"})

    return {"lines": lines, "context": {"state": "idle"}}


def _handle_slash(text: str) -> dict:
    cmd = text.lower().strip()
    if cmd in ("/help", "/"):
        return {
            "lines": [
                {"type": "resp", "text": "Available actions:"},
                {"type": "option", "text": "Paste a URL — import and index a webpage", "value": ""},
                {"type": "option", "text": "Type a question — search across all corpora", "value": ""},
                {"type": "option", "text": "/status — show your corpora stats", "value": "/status"},
                {"type": "option", "text": "/write — write a new source", "value": "/write"},
            ],
            "context": {"state": "idle"},
        }

    if cmd == "/status":
        corpora = list_corpora(include_private=True)
        if not corpora:
            return {"lines": [{"type": "resp", "text": "No corpora yet. Paste a URL to get started."}], "context": {"state": "idle"}}
        lines = [{"type": "resp", "text": f"{len(corpora)} corpora:"}]
        for c in corpora:
            lines.append({"type": "card", "label": c["name"], "status": c["status"].upper(),
                          "detail": f'{c["document_count"]} documents · {c["chunk_count"]} chunks · {c["word_count"]} words',
                          "corpus_id": c["id"]})
        return {"lines": lines, "context": {"state": "idle"}}

    if cmd == "/write":
        return {
            "lines": [{"type": "resp", "text": "Opening editor..."}],
            "context": {"state": "idle", "action": "open_write"},
        }

    if cmd == "/upload":
        return {
            "lines": [{"type": "resp", "text": "Opening file picker..."}],
            "context": {"state": "idle", "action": "open_upload"},
        }

    return {"lines": [{"type": "resp", "text": f'Unknown command: {text}. Type / for help.'}], "context": {"state": "idle"}}


def _handle_question(text: str) -> dict:
    """Chat with Noos: LLM-synthesized answer grounded in cross-corpus retrieval.

    Falls back to a raw search-result list if no LLM provider is configured
    (so the home terminal still gives useful output without API keys).
    """
    corpora = list_corpora(include_private=False)
    ready = [c for c in corpora if c.get("status") == "ready" and c.get("access_level") == "public"]

    if not ready:
        return {
            "lines": [{"type": "resp", "text": "Nothing indexed yet — paste a URL or drop a file to start."}],
            "context": {"state": "idle"},
        }

    from noosphere.core.chat import chat_with_noosphere

    try:
        result = chat_with_noosphere(text, top_k=5)
    except Exception as e:
        return {
            "lines": [{"type": "resp", "text": f"Error: {str(e)[:120]}"}],
            "context": {"state": "idle"},
        }

    response_text = (result.get("response") or "").strip()
    citations = result.get("citations", []) or []

    # No LLM configured → fall back to raw top-chunks display so the terminal
    # is still useful without API keys (e.g. on a demo install).
    if not response_text or response_text.startswith("No LLM provider"):
        from noosphere.core.retrieval import search_corpus
        all_results = []
        for c in ready:
            try:
                sr = search_corpus(c["id"], text, top_k=3, include_context=True)
                for r in sr.get("results", []):
                    r["corpus_name"] = c["name"]
                    all_results.append(r)
            except Exception:
                continue
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        top = all_results[:5]
        if not top:
            return {
                "lines": [{"type": "resp", "text": f'No matches for "{text}" across {len(ready)} corpora.'}],
                "context": {"state": "idle"},
            }
        lines = [{"type": "resp", "text": "Top matches (no LLM configured — showing raw chunks):"}]
        for r in top:
            chunk_text = r.get("text", "")
            if len(chunk_text) > 200:
                chunk_text = chunk_text[:200] + "..."
            cite = r.get("citation", {})
            title = cite.get("document_title", "") or chunk_text[:60]
            lines.append({
                "type": "search_result",
                "title": title,
                "text": chunk_text,
                "score": r.get("score", 0),
                "source": r.get("corpus_name", ""),
            })
        return {"lines": lines, "context": {"state": "idle"}}

    # Noos answer + compact sources footer
    lines = [{"type": "resp", "text": response_text}]
    if citations:
        source_names = []
        for c in citations[:5]:
            name = c.get("corpus_name") or c.get("title") or ""
            if name and name not in source_names:
                source_names.append(name)
        if source_names:
            lines.append({"type": "hint", "text": "Sources: " + " · ".join(source_names[:4])})
    return {"lines": lines, "context": {"state": "idle"}}
