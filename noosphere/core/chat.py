"""Chat with a corpus — RAG retrieval + LLM response generation."""

from noosphere.core.llm import call_llm
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
) -> dict:
    """Chat with a corpus using RAG.

    1. Retrieve relevant chunks from the corpus
    2. Send chunks + message to LLM
    3. Return the response with citations
    """
    retrieval = search_corpus(corpus_id, message, top_k=top_k)
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

    response_text = call_llm(messages)

    return {
        "response": response_text,
        "citations": citations,
        "chunks_used": len(chunks),
    }


def chat_with_noosphere(
    message: str,
    *,
    history: list[dict] | None = None,
    top_k: int = 5,
) -> dict:
    """Chat across ALL public corpora."""
    from noosphere.core.corpus import list_corpora

    corpora = [c for c in list_corpora() if c.get("status") == "ready" and c.get("access_level") == "public"]
    all_chunks = []

    for c in corpora:
        try:
            result = search_corpus(c["id"], message, top_k=3)
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

    response_text = call_llm(messages)

    return {
        "response": response_text,
        "citations": citations,
        "corpora_searched": len(corpora),
    }


# Backward-compat alias — knowledge_growth.py imports this
_call_llm = call_llm
