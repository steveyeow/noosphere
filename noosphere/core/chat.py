"""Chat with a corpus — RAG retrieval + LLM response generation."""

from noosphere.core.llm import call_llm as _call_llm
from noosphere.core.retrieval import search_corpus


SYSTEM_PROMPT = """You are a knowledgeable assistant that answers questions based on the provided source material.

Rules:
- Answer ONLY based on the provided sources. If the sources don't contain relevant information, say so.
- Cite your sources by mentioning the document title and date when available.
- Be concise and direct.
- Use the same language as the user's question."""


def chat_with_corpus(
    corpus_id: str,
    message: str,
    *,
    history: list[dict] | None = None,
    top_k: int = 5,
    caller: str = "owner",
) -> dict:
    """Chat with a corpus using RAG.

    1. Retrieve relevant chunks from the corpus
    2. Send chunks + message to LLM
    3. Return the response with citations

    caller gates source_kind filtering (see retrieval.search_corpus).
    """
    retrieval = search_corpus(corpus_id, message, top_k=top_k, caller=caller)
    chunks = retrieval.get("results", [])

    context_parts = []
    citations = []
    for i, chunk in enumerate(chunks):
        cite = chunk.get("citation", {})
        title = cite.get("document_title", f"Source {i+1}")
        date = cite.get("date", "")
        label = f"{title}" + (f" ({date})" if date else "")
        context_parts.append(f"[{label}]\n{chunk['text']}")
        citations.append({
            "title": title,
            "date": date,
            "document_id": cite.get("document_id", ""),
            "score": chunk.get("score", 0),
        })

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant sources found."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
    messages.append({
        "role": "user",
        "content": f"Sources:\n\n{context}\n\n---\n\nQuestion: {message}",
    })

    response_text = _call_llm(messages)

    return {
        "response": response_text,
        "citations": citations,
        "chunks_used": len(chunks),
    }


INTERVIEW_SYSTEM_PROMPT = """You are an inquisitive archivist interviewing the user to capture knowledge that lives only in their head.

You are NOT answering questions — you are ASKING them, to draw out what the user knows but has never written down.

Rules:
- Ask exactly ONE question at a time. Keep it short, specific, and easy to answer.
- Stay on the gap you're given. Draw out the user's first-hand knowledge, judgment, concrete detail, examples, and the "why" behind them.
- Build on the user's previous answers — go a level deeper rather than changing subject.
- Do not re-ask what the corpus already records. Do not lecture or summarize. No preamble — just the next good question.
- Warm and curious, never an interrogation.
- If the user signals they're done or has nothing more, thank them in one short line and stop asking.
- Use the same language as the user."""


def interview_with_corpus(
    corpus_id: str,
    gap: dict,
    *,
    message: str | None = None,
    history: list[dict] | None = None,
    top_k: int = 4,
) -> dict:
    """Run one turn of a gap-filling interview (inverted posture: the assistant
    asks the user to surface knowledge the corpus doesn't have yet).

    ``message=None`` → produce the opening question about the gap.
    ``message=<answer>`` → the user's latest answer; produce the next question.
    ``history`` is the prior turns (alternating assistant/user), excluding the
    current answer.
    """
    gap = gap or {}
    label = (gap.get("label") or "").strip()
    reason = (gap.get("reason") or "").strip()
    gkind = gap.get("kind") or "topic"

    # Light grounding: surface what the corpus already knows about this gap so
    # the interviewer asks for what's missing, not what's already on record.
    known = ""
    if label:
        try:
            retrieval = search_corpus(corpus_id, label, top_k=top_k, caller="owner")
            snips = [ch.get("text", "")[:400] for ch in retrieval.get("results", [])[:top_k]]
            known = "\n\n".join(s for s in snips if s)
        except Exception:
            known = ""

    seed = (
        f"You are interviewing the user to fill one gap in their knowledge base.\n"
        f"Gap ({gkind}): {label or '(this knowledge base)'}\n"
        f"Why it's a gap: {reason or 'it is thin or missing'}\n\n"
        f"What the corpus already records about it (do NOT re-ask these):\n"
        f"{known or '(nothing yet)'}"
    )

    messages = [{"role": "system", "content": INTERVIEW_SYSTEM_PROMPT}]
    if message is None:
        messages.append({"role": "user", "content": seed + "\n\nAsk your first question now."})
    else:
        messages.append({"role": "user", "content": seed})
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": message})

    response_text = _call_llm(messages)
    return {"response": response_text, "gap": gap}


def chat_with_noosphere(
    message: str,
    *,
    history: list[dict] | None = None,
    top_k: int = 5,
) -> dict:
    """Chat across ALL public corpora.

    Cross-corpus chat is always external w.r.t. each corpus — the caller is
    not a specific corpus owner, so source_kind filter applies.
    """
    from noosphere.core.corpus import list_corpora

    corpora = [c for c in list_corpora() if c.get("status") == "ready" and c.get("access_level") == "public"]
    all_chunks = []

    for c in corpora:
        try:
            result = search_corpus(c["id"], message, top_k=3, caller="external")
            for r in result.get("results", []):
                r["corpus_name"] = c["name"]
            all_chunks.extend(result.get("results", []))
        except Exception:
            continue

    all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
    top_chunks = all_chunks[:top_k]

    context_parts = []
    citations = []
    for i, chunk in enumerate(top_chunks):
        cite = chunk.get("citation", {})
        title = cite.get("document_title", f"Source {i+1}")
        corpus_name = chunk.get("corpus_name", "")
        date = cite.get("date", "")
        label = f"{title}" + (f" from {corpus_name}" if corpus_name else "") + (f" ({date})" if date else "")
        context_parts.append(f"[{label}]\n{chunk['text']}")
        citations.append({
            "title": title,
            "corpus_name": corpus_name,
            "date": date,
            "score": chunk.get("score", 0),
        })

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant sources found."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])
    messages.append({
        "role": "user",
        "content": f"Sources:\n\n{context}\n\n---\n\nQuestion: {message}",
    })

    response_text = _call_llm(messages)

    return {
        "response": response_text,
        "citations": citations,
        "corpora_searched": len(corpora),
    }
