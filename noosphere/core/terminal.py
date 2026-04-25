"""Terminal command handler — parses user input and routes to appropriate action."""

import re
from noosphere.core.corpus import list_corpora, create_corpus
from noosphere.core.ingest import ingest_url, ingest_text
from noosphere.core.indexer import index_corpus


def handle_terminal_input(text: str, context: dict | None = None, mode: str = "enrich") -> dict:
    """Process terminal input and return structured response.

    Home terminal is chat-first (you're talking to Noos). Routing:
      - URL → ingest into a corpus (with inline corpus picker)
      - /command → slash-command handler
      - mode='create' → spin up a new knowledge base named after the topic
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

    if mode == "create":
        return _handle_create(text)

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
        return _handle_concierge(text, has_corpora=bool(corpora))

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


_CREATE_INTENT_PROMPT = """The user is in 'Create knowledge base' composer mode in Noosphere — a personal knowledge OS where each knowledge base is a corpus of URLs, files, and notes the user can chat with like a wiki.

Read the user's input and decide what they want. Output ONE LINE of valid JSON:

  {"intent":"topic","name":"<2-5 word title>","reply":"<short confirmation in user's language>"}
    — they named a clear subject for a new knowledge base. The reply will be shown alongside a 'Created' card; keep it to one sentence inviting them to add a first source.

  {"intent":"chat","reply":"<conversational response in user's language>"}
    — they're asking what the app does, asking for help, or sent a vague request without a clear topic. Reply in 2-3 sentences. If they seem to want to create one but didn't name a topic, ask what topic. If they're asking about app capability, explain Create vs Enrich vs Compile mode briefly and invite them to name a topic.

Rules:
- Match the user's language (English, Chinese, etc.). Title-case English names; preserve case for other languages.
- Strip filler from names: "create me a corpus on harness engineering" → name "Harness Engineering".
- Output ONLY the JSON object — no preamble, no markdown fences, no trailing text.

Examples:
"AI product designing" → {"intent":"topic","name":"AI Product Design","reply":"Spinning up your AI Product Design knowledge base — paste a URL, drop a file, or write a note to add the first source."}
"创建一个产品设计的知识库" → {"intent":"topic","name":"产品设计","reply":"已经为你建好「产品设计」知识库 —— 贴一个链接、上传文件，或写一条笔记来添加第一个来源。"}
"create this corpus for me" → {"intent":"chat","reply":"Tell me what topic you'd like — for example 'founder playbook' or 'design systems' — and I'll spin up the knowledge base."}
"what can you do" → {"intent":"chat","reply":"You're in Create mode — name a topic and I'll start a knowledge base on it. Switch to Enrich to chat with what's already inside, or Compile to synthesize a wiki page from your sources."}"""


_CONCIERGE_PROMPT = """You are Noos, the in-app guide for Noosphere — a personal knowledge OS where users build a corpus of sources (URLs, files, notes) and chat with it like a wiki.

The user has no indexed sources yet, so you cannot cite anything. Your job:
- Plainly explain what they can do here when asked.
- If they name a topic, suggest creating a knowledge base on it: switch the composer to Create mode, or paste a URL / drop a file to seed one.
- Never invent facts about external topics. If they ask a factual question, say you can answer it once they add sources, and ask what kind of sources they have.
- Match the user's language. Keep it 2-4 sentences."""


def _classify_create_intent(text: str) -> dict | None:
    """Single LLM call: classify the input and emit a response. Returns
    {"intent": "topic"|"chat", ...} on success, or None if the LLM is
    unconfigured / errors / returns malformed JSON."""
    from noosphere.core.llm import call_llm
    import json as _json

    msgs = [
        {"role": "system", "content": _CREATE_INTENT_PROMPT},
        {"role": "user", "content": text.strip()},
    ]
    try:
        out = call_llm(msgs).strip()
    except Exception:
        return None
    # Strip markdown fences some providers wrap JSON in.
    out = re.sub(r"^```(?:json)?\s*", "", out).strip()
    out = re.sub(r"\s*```$", "", out).strip()
    try:
        data = _json.loads(out)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    intent = data.get("intent")
    if intent not in ("topic", "chat"):
        return None
    return data


def _handle_create(text: str) -> dict:
    """Create mode: ask the LLM to classify intent and respond.

    - intent='topic'  → create the corpus with the LLM-extracted name
    - intent='chat'   → return the LLM's conversational reply (no corpus)
    - LLM unavailable → graceful fallback so the user isn't dead-ended"""
    if not text:
        return _handle_concierge("", has_corpora=False)

    decision = _classify_create_intent(text)

    if decision and decision.get("intent") == "topic" and decision.get("name"):
        name = decision["name"][:60].rstrip()
        reply = (decision.get("reply") or "").strip()
        try:
            corpus = create_corpus(name, access_level="public")
        except Exception as e:
            return {
                "lines": [{"type": "resp", "text": f"Couldn't create that knowledge base: {str(e)[:120]}"}],
                "context": {"state": "idle"},
            }
        cid = corpus["id"]
        lines = [{"type": "card", "label": name, "status": "CREATED",
                  "detail": "New knowledge base — empty", "corpus_id": cid}]
        if reply:
            lines.append({"type": "resp", "text": reply})
        return {
            "lines": lines,
            "context": {
                "state": "idle",
                "action": "corpus_created",
                "corpus_id": cid,
                "corpus_name": name,
            },
        }

    if decision and decision.get("intent") == "chat" and decision.get("reply"):
        return {
            "lines": [{"type": "resp", "text": decision["reply"].strip()}],
            "context": {"state": "idle"},
        }

    # LLM completely unavailable. Defer to the concierge (also LLM-driven,
    # different prompt) — and if that also fails it has its own minimal
    # fallback. We never auto-create a corpus from raw text on this path,
    # because the input may well be a question, not a topic.
    return _handle_concierge(text, has_corpora=False)


def _handle_concierge(text: str, *, has_corpora: bool) -> dict:
    """Empty-state chat: respond conversationally instead of dead-ending.

    With no ready corpora the regular RAG path has nothing to retrieve, so
    we route the user's message to the LLM with an onboarding system prompt
    that explains capabilities and offers concrete next steps. If no LLM
    provider is configured we fall back to a one-line static hint."""
    from noosphere.core.llm import call_llm

    note = (
        " The user has at least one corpus, but none are ready yet (still indexing)."
        if has_corpora
        else " The user has not created any corpus yet."
    )
    msgs = [
        {"role": "system", "content": _CONCIERGE_PROMPT + note},
        {"role": "user", "content": text.strip()},
    ]
    try:
        reply = call_llm(msgs).strip()
    except Exception:
        reply = "Nothing indexed yet — switch to Create mode and name a topic, paste a URL, or drop a file to start."

    return {
        "lines": [{"type": "resp", "text": reply}],
        "context": {"state": "idle"},
    }
