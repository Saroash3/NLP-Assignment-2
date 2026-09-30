"""
Phase III cache tests: repeated queries hit the LRU cache, and re-running the
indexer invalidates cached results, so stale chunks are never served.
Uses a temporary docs folder + Chroma directory (the real index is untouched).
"""
import pytest

from rag import retriever
from rag.index import run_index
from rag.store import DB_DIR


@pytest.fixture
def temp_index(tmp_path):
    docs, db = tmp_path / "docs", tmp_path / "db"
    docs.mkdir()
    (docs / "guest.md").write_text("# Guest Policy\n\nA guest pass costs PKR 1,000 per visit.",
                                   encoding="utf-8")
    run_index(docs, db)
    retriever.clear_cache()
    retriever.load(db)
    yield docs, db
    retriever.clear_cache()
    retriever.load(DB_DIR)  # point the retriever back at the real index for other tests


def test_repeated_query_is_served_from_the_cache(temp_index):
    first = retriever.retrieve("How much is a guest pass?", k=1)
    hits_before = retriever.cache_info()["results"].hits
    second = retriever.retrieve("How much is a guest pass?", k=1)
    assert retriever.cache_info()["results"].hits == hits_before + 1
    assert first == second


def test_reindex_invalidates_cached_results(temp_index):
    docs, db = temp_index
    assert "1,000" in retriever.retrieve("How much is a guest pass?", k=1)[0]["text"]

    (docs / "guest.md").write_text("# Guest Policy\n\nA guest pass now costs PKR 1,500 per visit.",
                                   encoding="utf-8")
    run_index(docs, db)  # bumps the index version

    text = retriever.retrieve("How much is a guest pass?", k=1)[0]["text"]
    assert "1,500" in text and "1,000" not in text  # fresh chunk, not the stale cached one


def test_returned_results_are_copies(temp_index):
    result = retriever.retrieve("How much is a guest pass?", k=1)
    result[0]["text"] = "tampered"
    assert retriever.retrieve("How much is a guest pass?", k=1)[0]["text"] != "tampered"
