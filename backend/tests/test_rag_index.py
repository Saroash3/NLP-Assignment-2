"""
Phase I tests for rag/index.py: chunking rules and incremental re-indexing.
The indexing tests use a temporary docs folder and a temporary Chroma directory,
so they never touch the real index. (They load the real embedding model: ~10s.)
"""
from rag.index import MAX_WORDS, chunk_markdown, clean_for_embedding, n_words, run_index
from rag.store import get_collection

DOC = """# Late Fees

Intro sentence about instalments.

## Late fee
If the second instalment is more than 7 days late, a PKR 1,500 late fee is added.
"""


def test_every_chunk_is_prefixed_with_title_and_heading():
    chunks = chunk_markdown(DOC)
    assert len(chunks) == 1
    assert chunks[0]["text"].startswith("Late Fees")  # the title is always in the prefix
    assert "PKR 1,500" in chunks[0]["text"]


def test_long_document_splits_near_max_words_with_heading_prefix():
    sections = "\n\n".join(f"## Section {i}\n" + "word " * 60 for i in range(6))
    chunks = chunk_markdown(f"# Big Doc\n\n{sections}")
    assert len(chunks) > 1
    for c in chunks:
        assert c["text"].startswith("Big Doc > Section")  # the nearest heading is in the prefix
        assert n_words(c["text"]) <= MAX_WORDS + 10  # (+ prefix words)


def test_short_intro_is_not_left_as_a_tiny_chunk():
    table = "| a | b |\n|---|---|\n" + "\n".join(f"| row {i} | value {i} |" for i in range(40))
    chunks = chunk_markdown(f"# Prices\n\nShort intro.\n\n{table}")
    assert len(chunks) == 1  # the intro stays with the table instead of becoming its own chunk


def test_clean_for_embedding_strips_markdown_symbols():
    assert clean_for_embedding("| **Plus** | 16,000 |\n|---|---|").strip() == "Plus 16,000"


def test_incremental_index_add_update_delete(tmp_path):
    docs, db = tmp_path / "docs", tmp_path / "db"
    docs.mkdir()
    (docs / "a.md").write_text("# A\n\nAlpha document about freezing.", encoding="utf-8")
    (docs / "b.md").write_text("# B\n\nBeta document about guests.", encoding="utf-8")

    first = run_index(docs, db)
    assert sorted(first["added"]) == ["a.md", "b.md"]

    second = run_index(docs, db)  # nothing changed
    assert second["added"] == second["updated"] == second["removed"] == []
    assert second["unchanged"] == 2

    (docs / "a.md").write_text("# A\n\nAlpha document, EDITED.", encoding="utf-8")
    (docs / "b.md").unlink()
    third = run_index(docs, db)
    assert third["updated"] == ["a.md"] and third["removed"] == ["b.md"]

    collection = get_collection(db)
    assert collection.get(where={"source": "b.md"})["ids"] == []
    assert "EDITED" in collection.get(where={"source": "a.md"}, include=["documents"])["documents"][0]
