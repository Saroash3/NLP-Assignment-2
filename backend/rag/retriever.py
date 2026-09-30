"""
Online retrieval: embed the user's query and return the top-k most similar
chunks from Chroma, each with its source filename and a similarity score.

The embedding model and the Chroma collection are loaded ONCE (load() is called
at app startup), never per request.

CACHING (two LRU caches, both keyed on the exact text that is embedded -- i.e.
after the follow-up rule in the conversation manager):
  _embed_query : text -> embedding vector. Depends only on the model, so it stays
                 valid even when the documents change.
  _search      : (text, k, index_version) -> top-k chunks. index_version changes
                 whenever `python -m rag.index` changes anything, so after a
                 re-index every old entry simply stops matching: stale chunks are
                 never served, and the old entries age out of the LRU.
"""
import threading
from functools import lru_cache
from pathlib import Path

from rag.store import DB_DIR, embed, get_collection, index_version, load_model

TOP_K = 4  # the assignment asks for k >= 3


class RetrievalUnavailable(Exception):
    """The index can't answer at all (e.g. it was never built), as opposed to 'no match'."""

_model = None
_collection = None
_db_dir: Path = DB_DIR
_load_lock = threading.Lock()  # so concurrent first requests don't each load the model


def load(db_dir: Path = DB_DIR) -> None:
    """Load the embedding model and open the vector store (call once at startup)."""
    global _model, _collection, _db_dir
    with _load_lock:
        if db_dir != _db_dir:
            _collection, _db_dir = None, db_dir
        if _collection is None:
            # If the index folder is broken this raises -- and keeps raising on every request
            # (each caught and logged by the conversation manager) until the index is fixed.
            _collection = get_collection(_db_dir)
        if _model is None:
            _model = load_model()


@lru_cache(maxsize=512)
def _embed_query(text: str) -> tuple[float, ...]:
    return tuple(embed(_model, [text])[0])


@lru_cache(maxsize=256)
def _search(text: str, k: int, version: int) -> tuple[dict, ...]:
    # `version` isn't used in the body: it's only here so it becomes part of the cache key.
    # (Exceptions are never cached by lru_cache, so a fixed index works on the next call.)
    if _collection.count() == 0:
        raise RetrievalUnavailable("the index is empty -- run `python -m rag.index`")
    result = _collection.query(
        query_embeddings=[list(_embed_query(text))],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    return tuple(
        {
            "source": meta["source"],
            "section": meta["section"],
            "text": doc,
            # The collection uses cosine distance, so similarity = 1 - distance (1.0 = identical).
            "score": round(1 - dist, 3),
        }
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        )
    )


def retrieve(query: str, k: int = TOP_K) -> list[dict]:
    """Return the top-k chunks, best first: [{source, section, text, score}, ...]."""
    load(_db_dir)
    # Copies, so a caller modifying a result can never corrupt the cached entry.
    return [dict(c) for c in _search(query, k, index_version(_db_dir))]


def cache_info() -> dict:
    return {"embeddings": _embed_query.cache_info(), "results": _search.cache_info()}


def clear_cache() -> None:
    _embed_query.cache_clear()
    _search.cache_clear()
