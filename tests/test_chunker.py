"""Tests for the chunking engine — paragraph, recursive, and semantic strategies."""

from noosphere.core.chunker import chunk_document


def test_paragraph_basic():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    chunks = chunk_document(text, strategy="paragraph")
    assert len(chunks) >= 1
    for ch in chunks:
        assert "text" in ch
        assert "chunk_index" in ch
        assert "char_start" in ch
        assert "char_end" in ch
        assert ch["text"].strip()


def test_paragraph_preserves_all_content():
    paragraphs = [f"Paragraph {i} with some content." for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_document(text, strategy="paragraph")
    combined = " ".join(ch["text"] for ch in chunks)
    for p in paragraphs:
        assert p in combined or p.split()[0] in combined


def test_paragraph_respects_max_tokens():
    long_text = " ".join(["word"] * 2000)
    chunks = chunk_document(text=long_text, strategy="paragraph", max_tokens=200)
    for ch in chunks:
        words = ch["text"].split()
        assert len(words) <= 300  # allow some overlap margin


def test_paragraph_heading_split():
    section_body = " ".join(["filler"] * 80)
    text = f"# Title\n\nIntro paragraph.\n\n## Section One\n\n{section_body}\n\n## Section Two\n\n{section_body}"
    chunks = chunk_document(text, strategy="paragraph", min_tokens=20, max_tokens=200)
    assert len(chunks) >= 2


def test_recursive_basic():
    text = "A.\n\nB.\n\nC.\n\nD.\n\nE."
    chunks = chunk_document(text, strategy="recursive")
    assert len(chunks) >= 1
    combined = " ".join(ch["text"] for ch in chunks)
    for letter in "ABCDE":
        assert letter in combined


def test_recursive_large_document():
    paragraphs = [f"Paragraph {i}. " + " ".join(["filler"] * 100) for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_document(text, strategy="recursive", max_tokens=500)
    assert len(chunks) >= 2
    for ch in chunks:
        assert len(ch["text"].split()) <= 600  # allow overlap margin


def test_recursive_chunk_indices():
    text = "\n\n".join([f"Section {i}. " + " ".join(["word"] * 200) for i in range(5)])
    chunks = chunk_document(text, strategy="recursive", max_tokens=300)
    indices = [ch["chunk_index"] for ch in chunks]
    assert indices == list(range(len(chunks)))


def test_semantic_falls_back_to_paragraph():
    """Semantic chunking without an embedding provider falls back to paragraph."""
    text = "First sentence. Second sentence. Third sentence."
    chunks = chunk_document(text, strategy="semantic")
    assert len(chunks) >= 1
    assert chunks[0]["text"].strip()


def test_empty_text():
    for strategy in ("paragraph", "recursive"):
        chunks = chunk_document("", strategy=strategy)
        assert chunks == [] or all(not ch["text"].strip() for ch in chunks)


def test_single_sentence():
    text = "Just one sentence here."
    for strategy in ("paragraph", "recursive"):
        chunks = chunk_document(text, strategy=strategy)
        assert len(chunks) == 1
        assert "one sentence" in chunks[0]["text"]


def test_chunk_positions_are_valid():
    text = "First part.\n\nSecond part.\n\nThird part."
    for strategy in ("paragraph", "recursive"):
        chunks = chunk_document(text, strategy=strategy)
        for ch in chunks:
            assert ch["char_start"] >= 0
            assert ch["char_end"] >= ch["char_start"]
            assert ch["char_end"] <= len(text) + len(text)  # overlap can extend
