"""Chunking engine — split documents into retrievable segments.

Three strategies:
  paragraph  — split on headings + paragraphs, merge small, split oversized (default)
  recursive  — 5-level delimiter hierarchy, larger chunks with overlap (transcripts, timelines)
  semantic   — embed sentences, find topic boundaries by cosine drops (papers, essays)
"""

import re
from noosphere.core.config import CHUNK_MIN_TOKENS, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS

RECURSIVE_DELIMITERS = ["\n\n\n", "\n\n", "\n", ". ", " "]
RECURSIVE_MAX_TOKENS = 500
RECURSIVE_OVERLAP_TOKENS = 80
SEMANTIC_MIN_SENTENCES = 3


def _approx_tokens(text: str) -> int:
    return len(text.split())


def chunk_document(
    text: str,
    *,
    strategy: str = "paragraph",
    min_tokens: int = 0,
    max_tokens: int = 0,
    overlap_tokens: int = 0,
) -> list[dict]:
    """Split document text into chunks using the specified strategy.

    Returns list of dicts with keys: text, char_start, char_end, chunk_index.
    """
    if strategy == "recursive":
        return _chunk_recursive(text, max_tokens or RECURSIVE_MAX_TOKENS, overlap_tokens or RECURSIVE_OVERLAP_TOKENS)
    elif strategy == "semantic":
        result = _chunk_semantic(text, max_tokens or CHUNK_MAX_TOKENS, min_tokens or CHUNK_MIN_TOKENS)
        if result is not None:
            return result
        return _chunk_paragraph(text, min_tokens or CHUNK_MIN_TOKENS, max_tokens or CHUNK_MAX_TOKENS, overlap_tokens or CHUNK_OVERLAP_TOKENS)
    else:
        return _chunk_paragraph(text, min_tokens or CHUNK_MIN_TOKENS, max_tokens or CHUNK_MAX_TOKENS, overlap_tokens or CHUNK_OVERLAP_TOKENS)


# ── Strategy: paragraph (original, default) ─────────────────────────

def _chunk_paragraph(text: str, min_tok: int, max_tok: int, overlap: int) -> list[dict]:
    sections = _split_by_headings_and_paragraphs(text)
    merged = _merge_small_sections(sections, min_tok, max_tok)
    final = _split_oversized(merged, max_tok, overlap)
    return _assign_positions(text, final)


def _split_by_headings_and_paragraphs(text: str) -> list[dict]:
    pattern = r"(?=\n#{1,3}\s)|\n{2,}"
    parts = re.split(pattern, text)
    sections = []
    pos = 0
    for part in parts:
        part = part.strip()
        if not part:
            pos = text.find(part, pos) + len(part) if part else pos
            continue
        start = text.find(part[:80], pos)
        if start == -1:
            start = pos
        sections.append({"text": part, "char_start": start, "char_end": start + len(part)})
        pos = start + len(part)
    return sections


def _merge_small_sections(sections: list[dict], min_tokens: int, max_tokens: int) -> list[dict]:
    if not sections:
        return []

    merged = [sections[0].copy()]
    for sec in sections[1:]:
        last = merged[-1]
        combined_tokens = _approx_tokens(last["text"]) + _approx_tokens(sec["text"])
        if _approx_tokens(last["text"]) < min_tokens and combined_tokens <= max_tokens:
            last["text"] = last["text"] + "\n\n" + sec["text"]
            last["char_end"] = sec["char_end"]
        else:
            merged.append(sec.copy())

    return merged


def _split_oversized(sections: list[dict], max_tokens: int, overlap_tokens: int) -> list[dict]:
    result = []
    for sec in sections:
        if _approx_tokens(sec["text"]) <= max_tokens:
            result.append(sec)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", sec["text"])
        if len(sentences) <= 1 and _approx_tokens(sec["text"]) > max_tokens:
            result.extend(_split_by_words(sec, max_tokens, overlap_tokens))
            continue

        current_text = ""
        for sent in sentences:
            if _approx_tokens(current_text + " " + sent) > max_tokens and current_text:
                result.append({
                    "text": current_text.strip(),
                    "char_start": sec["char_start"],
                    "char_end": sec["char_start"] + len(current_text),
                })
                words = current_text.split()
                overlap_text = " ".join(words[-overlap_tokens:]) if len(words) > overlap_tokens else ""
                current_text = overlap_text + " " + sent
            else:
                current_text = (current_text + " " + sent).strip()

        if current_text.strip():
            if _approx_tokens(current_text) > max_tokens:
                result.extend(_split_by_words(
                    {"text": current_text.strip(), "char_start": sec["char_start"], "char_end": sec["char_end"]},
                    max_tokens, overlap_tokens,
                ))
            else:
                result.append({
                    "text": current_text.strip(),
                    "char_start": sec["char_start"],
                    "char_end": sec["char_end"],
                })

    return result


def _split_by_words(sec: dict, max_tokens: int, overlap_tokens: int) -> list[dict]:
    """Last-resort split: cut by word count when no sentence boundaries exist."""
    words = sec["text"].split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append({
            "text": chunk_text,
            "char_start": sec["char_start"],
            "char_end": sec["char_end"],
        })
        start = end - overlap_tokens if end < len(words) else len(words)
    return chunks


# ── Strategy: recursive (5-level delimiter hierarchy) ───────────────

def _chunk_recursive(text: str, max_tokens: int, overlap_tokens: int) -> list[dict]:
    """Split using a hierarchy of delimiters for maximum context preservation."""
    raw_chunks = _recursive_split(text, RECURSIVE_DELIMITERS, max_tokens)

    final = []
    prev_overlap = ""
    for chunk_text in raw_chunks:
        if not chunk_text.strip():
            continue
        combined = (prev_overlap + " " + chunk_text).strip() if prev_overlap else chunk_text.strip()
        final.append({"text": combined})

        words = chunk_text.split()
        prev_overlap = " ".join(words[-overlap_tokens:]) if len(words) > overlap_tokens else ""

    return _assign_positions(text, final)


def _recursive_split(text: str, delimiters: list[str], max_tokens: int) -> list[str]:
    """Recursively split text using increasingly fine-grained delimiters."""
    if _approx_tokens(text) <= max_tokens:
        return [text]

    if not delimiters:
        words = text.split()
        chunks = []
        for i in range(0, len(words), max_tokens):
            chunks.append(" ".join(words[i:i + max_tokens]))
        return chunks

    sep = delimiters[0]
    parts = text.split(sep)
    remaining_delimiters = delimiters[1:]

    chunks = []
    current = ""
    for part in parts:
        candidate = current + sep + part if current else part
        if _approx_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if _approx_tokens(part) > max_tokens:
                sub = _recursive_split(part, remaining_delimiters, max_tokens)
                chunks.extend(sub)
                current = ""
            else:
                current = part

    if current:
        chunks.append(current)

    return chunks


# ── Strategy: semantic (sentence-level cosine boundary detection) ───

def _chunk_semantic(text: str, max_tokens: int, min_tokens: int) -> list[dict] | None:
    """Split by detecting topic boundaries from sentence embedding similarity.

    Returns None if embedding fails (caller should fall back to paragraph).
    """
    sentences = _split_sentences(text)
    if len(sentences) < SEMANTIC_MIN_SENTENCES:
        return None

    try:
        from noosphere.core.embeddings import get_embedder
        embedder = get_embedder()
        vecs = embedder.embed([s["text"] for s in sentences])
    except Exception:
        return None

    import numpy as np
    similarities = []
    for i in range(len(vecs) - 1):
        a, b = vecs[i], vecs[i + 1]
        norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            similarities.append(0.0)
        else:
            similarities.append(float(np.dot(a, b) / (norm_a * norm_b)))

    if not similarities:
        return None

    boundaries = _find_boundaries(similarities)

    groups = []
    current_sents = [sentences[0]]
    for i in range(1, len(sentences)):
        if (i - 1) in boundaries and _approx_tokens(" ".join(s["text"] for s in current_sents)) >= min_tokens:
            groups.append(current_sents)
            current_sents = []
        current_sents.append(sentences[i])

        if _approx_tokens(" ".join(s["text"] for s in current_sents)) >= max_tokens:
            groups.append(current_sents)
            current_sents = []

    if current_sents:
        if groups and _approx_tokens(" ".join(s["text"] for s in current_sents)) < min_tokens:
            groups[-1].extend(current_sents)
        else:
            groups.append(current_sents)

    chunks = []
    for group in groups:
        chunk_text = " ".join(s["text"] for s in group)
        chunks.append({"text": chunk_text.strip()})

    return _assign_positions(text, chunks)


def _split_sentences(text: str) -> list[dict]:
    """Split text into sentences with position tracking."""
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    pos = 0
    for s in raw:
        s = s.strip()
        if not s:
            continue
        start = text.find(s[:50], pos)
        if start == -1:
            start = pos
        sentences.append({"text": s, "char_start": start, "char_end": start + len(s)})
        pos = start + len(s)
    return sentences


def _find_boundaries(similarities: list[float], *, threshold_percentile: float = 25.0) -> set[int]:
    """Find topic boundary indices where similarity drops below a threshold.

    Uses percentile-based thresholding for robustness.
    """
    if not similarities:
        return set()

    sorted_sims = sorted(similarities)
    idx = int(len(sorted_sims) * threshold_percentile / 100.0)
    threshold = sorted_sims[min(idx, len(sorted_sims) - 1)]

    boundaries = set()
    for i, sim in enumerate(similarities):
        if sim <= threshold:
            boundaries.add(i)

    return boundaries


# ── Shared utilities ────────────────────────────────────────────────

def _assign_positions(full_text: str, chunks: list[dict]) -> list[dict]:
    """Assign char_start, char_end, and chunk_index to chunk list."""
    result = []
    search_from = 0
    for i, ch in enumerate(chunks):
        text = ch["text"]
        if "char_start" in ch and ch["char_start"] is not None:
            start = ch["char_start"]
        else:
            start = full_text.find(text[:80], search_from)
            if start == -1:
                start = search_from

        result.append({
            "text": text,
            "char_start": start,
            "char_end": start + len(text),
            "chunk_index": i,
        })
        search_from = start + len(text)

    return result
