"""Semantic chunking engine — split documents into retrievable segments."""

import re
from noosphere.core.config import CHUNK_MIN_TOKENS, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS


def _approx_tokens(text: str) -> int:
    return len(text.split())


def chunk_document(
    text: str,
    *,
    min_tokens: int = 0,
    max_tokens: int = 0,
    overlap_tokens: int = 0,
) -> list[dict]:
    """Split document text into semantic chunks.

    Returns list of dicts with keys: text, char_start, char_end, chunk_index.
    Strategy: split on paragraph/heading boundaries, then merge small chunks
    and split oversized ones.
    """
    min_tok = min_tokens or CHUNK_MIN_TOKENS
    max_tok = max_tokens or CHUNK_MAX_TOKENS
    overlap = overlap_tokens or CHUNK_OVERLAP_TOKENS

    sections = _split_by_headings_and_paragraphs(text)
    merged = _merge_small_sections(sections, min_tok, max_tok)
    final = _split_oversized(merged, max_tok, overlap)

    chunks = []
    for i, segment in enumerate(final):
        start = text.find(segment["text"][:80])
        if start == -1:
            start = segment.get("char_start", 0)
        chunks.append({
            "text": segment["text"],
            "char_start": start,
            "char_end": start + len(segment["text"]),
            "chunk_index": i,
        })

    return chunks


def _split_by_headings_and_paragraphs(text: str) -> list[dict]:
    """Split text at Markdown headings (## / ###) and double newlines."""
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
    """Merge consecutive sections that are below min_tokens."""
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
    """Split sections that exceed max_tokens by sentence boundaries."""
    result = []
    for sec in sections:
        if _approx_tokens(sec["text"]) <= max_tokens:
            result.append(sec)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", sec["text"])
        current_text = ""
        for sent in sentences:
            if _approx_tokens(current_text + " " + sent) > max_tokens and current_text:
                result.append({
                    "text": current_text.strip(),
                    "char_start": sec["char_start"],
                    "char_end": sec["char_start"] + len(current_text),
                })
                # Overlap: keep last few words
                words = current_text.split()
                overlap_text = " ".join(words[-overlap_tokens:]) if len(words) > overlap_tokens else ""
                current_text = overlap_text + " " + sent
            else:
                current_text = (current_text + " " + sent).strip()

        if current_text.strip():
            result.append({
                "text": current_text.strip(),
                "char_start": sec["char_start"],
                "char_end": sec["char_end"],
            })

    return result
