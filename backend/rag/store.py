"""
Shared pieces of the RAG module: file locations, the embedding model and
the Chroma collection. Both the offline indexer (index.py) and the online
retriever (retriever.py) import from here, so they can never disagree about
which model or which collection is being used.
"""
import os
import time
from pathlib import Path

# Quieter logs on Windows (symlink warning, weight-loading progress bars).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

import chromadb  # noqa: E402
from chromadb.config import Settings  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "documents"
DB_DIR = Path(__file__).resolve().parent / "chroma_db"  # persistent, git-ignored

# all-MiniLM-L6-v2: small (~90 MB), fast on CPU, 384-dim vectors, good quality
# for short English passages. Runs locally -- no API calls.
EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "zor_docs"


def load_model() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL_NAME, device="cpu")


def embed(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    # normalize=True makes every vector length 1, so cosine similarity is just a dot product.
    return model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def index_version(db_dir: Path = DB_DIR) -> int:
    """A number that changes every time the index content changes (the marker file's
    modification time). The retriever puts it in its cache key -- see retriever.py."""
    try:
        return (db_dir / "index_version.txt").stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def bump_index_version(db_dir: Path = DB_DIR) -> None:
    """Called by the indexer after it added, updated or removed anything."""
    (db_dir / "index_version.txt").write_text(str(time.time_ns()), encoding="utf-8")


def get_collection(db_dir: Path = DB_DIR):
    client = chromadb.PersistentClient(
        path=str(db_dir), settings=Settings(anonymized_telemetry=False)
    )
    # embedding_function=None: we always pass our own vectors, so Chroma never
    # downloads or runs its own default model. "cosine" = distance is 1 - cosine similarity.
    return client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=None, metadata={"hnsw:space": "cosine"}
    )
