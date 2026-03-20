"""Terminal command handler — parses user input and routes to appropriate action."""

import re
from noosphere.core.corpus import list_corpora, create_corpus
from noosphere.core.ingest import ingest_url, ingest_text, _update_corpus_counts
from noosphere.core.indexer import index_corpus


def handle_terminal_input(text: str, context: dict | None = None) -> dict:
    """Process terminal input and return structured response.

    Context tracks conversation state (e.g. waiting for corpus selection).
    Returns dict with 'lines' (list of response items) and 'context' (updated state).
    """
    text = text.strip()
    ctx = context or {}
    state = ctx.get("state", "idle")

    if state == "pick_corpus":
        return _handle_corpus_pick(text, ctx)

    if state == "confirm_write":
        return _handle_write_confirm(text, ctx)

    if _is_url(text):
        return _handle_url(text)

    if text.startswith("/"):
        return _handle_slash(text)

    if len(text) > 20 and not text.endswith("?"):
        return _suggest_write_or_search(text)

    if text.endswith("?") or text.lower().startswith(("how", "what", "why", "when", "where", "who", "tell", "explain")):
        return _handle_question(text)

    return {
        "lines": [
            {"type": "resp", "text": f'Not sure what to do with "{text}". Try:'},
            {"type": "hint", "text": "Paste a URL to import, ask a question, or type / for shortcuts"},
        ],
        "context": {"state": "idle"},
    }


def _is_url(text: str) -> bool:
    return bool(re.match(r'https?://', text.strip()))


def _handle_url(url: str) -> dict:
    lines = [{"type": "resp", "text": f"Fetching {url}..."}]

    corpora = list_corpora()
    if not corpora:
        try:
            corpus = create_corpus("My Knowledge", access_level="public")
            doc = ingest_url(corpus["id"], url)
            result = index_corpus(corpus["id"])
            lines.extend([
                {"type": "resp", "text": f'✓ Extracted: "{doc["title"]}"'},
                {"type": "resp", "text": f'✓ {doc["word_count"]} words'},
                {"type": "resp", "text": "Created new corpus: My Knowledge"},
                {"type": "resp", "text": f"✓ Indexed: {result['chunk_count']} chunks"},
                {"type": "card", "label": "Source Added", "status": "READY",
                 "detail": f'{doc["title"]} · {doc["word_count"]} words',
                 "val": f'Corpus: My Knowledge · {result["chunk_count"]} chunks',
                 "corpus_id": corpus["id"]},
                {"type": "resp", "text": "Agents can now discover and cite this content."},
            ])
            return {"lines": lines, "context": {"state": "idle"}}
        except Exception as e:
            lines.append({"type": "resp", "text": f"✗ Failed: {str(e)[:100]}"})
            return {"lines": lines, "context": {"state": "idle"}}

    lines.append({"type": "resp", "text": "Add to which corpus?"})
    for i, c in enumerate(corpora):
        lines.append({"type": "option", "text": f"[{i+1}] {c['name']} ({c['document_count']} sources)", "value": str(i+1)})
    lines.append({"type": "option", "text": f"[{len(corpora)+1}] Create new corpus", "value": str(len(corpora)+1)})

    return {
        "lines": lines,
        "context": {"state": "pick_corpus", "url": url, "corpora_ids": [c["id"] for c in corpora]},
    }


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
            lines.append({"type": "resp", "text": f'✓ Extracted: "{doc["title"]}"'})
            lines.append({"type": "resp", "text": f'✓ {doc["word_count"]} words'})
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
        corpora = list_corpora()
        if not corpora:
            return {"lines": [{"type": "resp", "text": "No corpora yet. Paste a URL to get started."}], "context": {"state": "idle"}}
        lines = [{"type": "resp", "text": f"{len(corpora)} corpora:"}]
        for c in corpora:
            lines.append({"type": "card", "label": c["name"], "status": c["status"].upper(),
                          "detail": f'{c["document_count"]} sources · {c["chunk_count"]} chunks · {c["word_count"]} words',
                          "corpus_id": c["id"]})
        return {"lines": lines, "context": {"state": "idle"}}

    if cmd == "/write":
        return {
            "lines": [{"type": "resp", "text": "Opening editor..."}],
            "context": {"state": "idle", "action": "open_write"},
        }

    return {"lines": [{"type": "resp", "text": f'Unknown command: {text}. Type / for help.'}], "context": {"state": "idle"}}


def _suggest_write_or_search(text: str) -> dict:
    return {
        "lines": [
            {"type": "resp", "text": "What would you like to do with this?"},
            {"type": "option", "text": "[1] Save as a new source in a corpus", "value": "1"},
            {"type": "option", "text": "[2] Search this across the Noosphere", "value": "2"},
        ],
        "context": {"state": "confirm_write", "original_text": text},
    }


def _handle_write_confirm(text: str, ctx: dict) -> dict:
    original = ctx.get("original_text", "")
    if text.strip() == "1":
        corpora = list_corpora()
        if not corpora:
            corpus = create_corpus("My Knowledge", access_level="public")
            doc = ingest_text(corpus["id"], title="Note", content=original)
            result = index_corpus(corpus["id"])
            return {
                "lines": [
                    {"type": "resp", "text": f'✓ Saved as source in "My Knowledge"'},
                    {"type": "resp", "text": f"✓ Indexed: {result['chunk_count']} chunks"},
                    {"type": "card", "label": "Source Added", "status": "READY",
                     "detail": f'My Knowledge · {result["chunk_count"]} chunks',
                     "corpus_id": corpus["id"]},
                ],
                "context": {"state": "idle"},
            }
        lines = [{"type": "resp", "text": "Add to which corpus?"}]
        for i, c in enumerate(corpora):
            lines.append({"type": "option", "text": f"[{i+1}] {c['name']}", "value": str(i+1)})
        lines.append({"type": "option", "text": f"[{len(corpora)+1}] Create new corpus", "value": str(len(corpora)+1)})
        return {"lines": lines, "context": {"state": "pick_corpus", "write_content": original, "write_title": "Note", "corpora_ids": [c["id"] for c in corpora]}}

    if text.strip() == "2":
        from noosphere.core.chat import chat_with_noosphere
        result = chat_with_noosphere(original)
        lines = [{"type": "resp", "text": result["response"]}]
        if result.get("citations"):
            cite_names = list(dict.fromkeys(
                c.get("corpus_name") or c.get("title", "") for c in result["citations"] if c.get("corpus_name") or c.get("title")
            ))
            if cite_names:
                lines.append({"type": "resp", "text": "Sources: " + " · ".join(cite_names)})
        return {"lines": lines, "context": {"state": "idle"}}

    return {"lines": [{"type": "resp", "text": "Please enter 1 or 2."}], "context": ctx}


def _handle_question(text: str) -> dict:
    try:
        from noosphere.core.chat import chat_with_noosphere
        result = chat_with_noosphere(text)
        lines = [{"type": "resp", "text": result["response"]}]
        if result.get("citations"):
            cite_names = list(dict.fromkeys(
                c.get("corpus_name") or c.get("title", "") for c in result["citations"] if c.get("corpus_name") or c.get("title")
            ))
            if cite_names:
                lines.append({"type": "resp", "text": "Sources: " + " · ".join(cite_names)})
        return {"lines": lines, "context": {"state": "idle"}}
    except Exception as e:
        return {"lines": [{"type": "resp", "text": f"Search failed: {str(e)[:80]}"}], "context": {"state": "idle"}}
