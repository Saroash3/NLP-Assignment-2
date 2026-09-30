"""
Offline indexing pipeline: documents/*.md -> chunks -> embeddings -> Chroma.

Re-runnable: each chunk stores the SHA-256 hash of the file it came from.
On every run we compare hashes and only touch what changed:
  new file      -> chunk + embed + add
  changed file  -> delete its old chunks, then chunk + embed + add
  deleted file  -> delete its chunks
  unchanged     -> skip (no embedding work at all)

Usage (from backend/):  python -m rag.index [--samples 3]
"""
import argparse
import hashlib
import re
import statistics
import sys
from pathlib import Path

from rag.store import DB_DIR, DOCS_DIR, bump_index_version, embed, get_collection, load_model

# CHUNKING STRATEGY (heading/paragraph aware):
# - Split each markdown file into blocks at blank lines (a paragraph, a list or a table).
# - Fill a chunk with whole blocks up to MAX_WORDS (150). Blocks are never cut in the
#   middle, so a price table or a list of rules stays together.
# - Prefer to start a new chunk at a heading once the current chunk has MIN_WORDS (80).
#   Sections stay whole, and we avoid tiny chunks.
# - Overlap: when a chunk has to be cut mid-section, its last short block
#   (<= OVERLAP_WORDS) is repeated at the start of the next chunk, so context isn't lost
#   at the boundary.
# - Every chunk's text is prefixed with "<document title> > <nearest heading>", so even
#   a chunk like "Late fee is PKR 1,500" knows which document and topic it belongs to.
#   That improves both retrieval and the LLM's reading of the chunk.
# Why 80-150 words (not 200-300): all-MiniLM-L6-v2 only embeds the first 256 tokens,
# and our markdown averages ~1.7 tokens per word (tables, **bold**, "PKR 12,000").
# Measured on our corpus: with 150-300 word chunks, 64% of chunks were truncated (their
# tail was invisible to retrieval); with 80-150 words + clean_for_embedding(), only 5% are.
MIN_WORDS = 80
MAX_WORDS = 150
OVERLAP_WORDS = 40
# Part of every file's stored hash: bump it when the chunking/formatting code changes,
# so the next run re-indexes every file even though the files themselves didn't change.
CHUNKER_VERSION = "2-linearized-tables"


def n_words(text: str) -> int:
    return len(text.split())


def linearize_tables(text: str) -> str:
    """
    Turn each markdown table row into one self-describing line:
      | Area | Mon–Sat | Sunday |          - Area: Ladies Wing; Mon–Sat: 8:00am–9:00pm; Sunday: Closed
      | Ladies Wing | 8:00am–9:00pm | Closed |   ->
    A small LLM misreads grids (it attached the Ladies Wing's "Closed" to the whole
    branch); with the column names repeated on every row, each fact stands alone.
    """
    lines, header = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            header = None  # a table ended
            lines.append(line)
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells  # first row of a table = column names
        elif not all(set(c) <= set("-: ") for c in cells):  # skip the |---|---| row
            lines.append("- " + "; ".join(f"{h}: {c}" for h, c in zip(header, cells)))
    return "\n".join(lines)


def chunk_markdown(text: str) -> list[dict]:
    """Split one markdown document into chunks: [{"section": str, "text": str}, ...]."""
    text = linearize_tables(text)
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    title = blocks[0].lstrip("# ").strip() if blocks and blocks[0].startswith("# ") else ""
    if title:
        blocks = blocks[1:]  # the title goes into every chunk's prefix instead

    groups: list[dict] = []  # each: {"section": nearest heading, "blocks": [...]}
    current: list[str] = []  # blocks in the chunk being built
    current_section = title  # nearest heading at the start of the current chunk
    section = title  # most recent heading seen so far

    for block in blocks:
        is_heading = block.startswith("#")
        size = sum(n_words(b) for b in current)

        # Only ever cut a chunk that already has MIN_WORDS, so no tiny chunks.
        # (A single large block, e.g. a price table, is kept whole even above MAX_WORDS.)
        if current and size >= MIN_WORDS and (is_heading or size + n_words(block) > MAX_WORDS):
            groups.append({"section": current_section, "blocks": current})
            last = current[-1]
            # Overlap only when cutting mid-section: repeat a short last paragraph.
            overlap = not is_heading and n_words(last) <= OVERLAP_WORDS and not last.startswith("#")
            current = [last] if overlap else []

        if is_heading:
            section = block.splitlines()[0].lstrip("# ").strip()
        if not current:
            current_section = section
        current.append(block)

    if current:
        # A short tail (e.g. a 20-word closing note) is merged into the previous chunk.
        if groups and sum(n_words(b) for b in current) < MIN_WORDS // 2:
            groups[-1]["blocks"] += current
        else:
            groups.append({"section": current_section, "blocks": current})

    chunks = []
    for g in groups:
        prefix = title if g["section"] == title else f"{title} > {g['section']}"
        chunks.append({"section": g["section"], "text": prefix + "\n\n" + "\n\n".join(g["blocks"])})
    return chunks


def clean_for_embedding(text: str) -> str:
    """Strip markdown-only symbols (table rules and pipes, **bold**, #) that waste the
    model's 256-token budget. Only the EMBEDDED text is cleaned; Chroma stores the
    original chunk, which is what the LLM will see."""
    text = re.sub(r"\|?-{3,}\|?", " ", text)  # table separator rows like |---|---|
    text = text.replace("|", " ").replace("**", "").replace("#", "")
    return re.sub(r"[ \t]+", " ", text)


def file_hash(path: Path) -> str:
    return hashlib.sha256(CHUNKER_VERSION.encode() + path.read_bytes()).hexdigest()


def run_index(docs_dir: Path = DOCS_DIR, db_dir: Path = DB_DIR) -> dict:
    """Bring the Chroma collection in line with docs_dir. Returns a summary dict."""
    collection = get_collection(db_dir)

    # What is already indexed: source filename -> hash (from chunk metadata).
    indexed: dict[str, str] = {}
    for meta in collection.get(include=["metadatas"])["metadatas"]:
        indexed[meta["source"]] = meta["file_hash"]

    on_disk = {p.name: p for p in sorted(docs_dir.glob("*.md"))}
    summary = {"added": [], "updated": [], "removed": [], "unchanged": 0}
    model = None  # loaded lazily: a no-change run never loads the model at all

    # 1. Deleted files: remove their chunks.
    for source in sorted(set(indexed) - set(on_disk)):
        collection.delete(where={"source": source})
        summary["removed"].append(source)

    # 2. New or changed files: (re)chunk, embed and add.
    for source, path in on_disk.items():
        digest = file_hash(path)
        if indexed.get(source) == digest:
            summary["unchanged"] += 1
            continue
        if source in indexed:
            collection.delete(where={"source": source})  # drop the old version's chunks
            summary["updated"].append(source)
        else:
            summary["added"].append(source)

        chunks = chunk_markdown(path.read_text(encoding="utf-8"))
        model = model or load_model()
        collection.add(
            ids=[f"{source}::{i}" for i in range(len(chunks))],
            documents=[c["text"] for c in chunks],
            embeddings=embed(model, [clean_for_embedding(c["text"]) for c in chunks]),
            metadatas=[
                {"source": source, "chunk_id": i, "section": c["section"], "file_hash": digest}
                for i, c in enumerate(chunks)
            ],
        )

    if summary["added"] or summary["updated"] or summary["removed"]:
        bump_index_version(db_dir)  # makes the running server's result cache miss (no stale chunks)
    summary["total_chunks"] = collection.count()
    return summary


def print_stats(db_dir: Path = DB_DIR, samples: int = 0) -> None:
    """Chunk statistics, so we can check the chunking is sensible."""
    data = get_collection(db_dir).get(include=["documents", "metadatas"])
    words = [n_words(d) for d in data["documents"]]
    per_doc: dict[str, int] = {}
    for meta in data["metadatas"]:
        per_doc[meta["source"]] = per_doc.get(meta["source"], 0) + 1

    print(f"\nChunks: {len(words)} from {len(per_doc)} documents")
    print(f"Words per chunk: avg {statistics.mean(words):.0f}, median {statistics.median(words):.0f}, "
          f"min {min(words)}, max {max(words)}")
    histogram = {k: list(per_doc.values()).count(k) for k in sorted(set(per_doc.values()))}
    print("Chunks per document (chunks: number of docs):", histogram)
    print("Per document:", ", ".join(f"{s}={n}" for s, n in sorted(per_doc.items())))

    for i in range(min(samples, len(words))):
        idx = (i * len(words)) // samples  # spread the samples across the collection
        meta = data["metadatas"][idx]
        print(f"\n--- Sample chunk {i + 1}: {meta['source']} #{meta['chunk_id']} "
              f"({words[idx]} words) ---\n{data['documents'][idx]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index documents/ into Chroma.")
    parser.add_argument("--samples", type=int, default=0, help="print N sample chunks")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 ("–" -> "�")

    result = run_index()
    print(f"Added:     {len(result['added'])} {result['added'] if len(result['added']) <= 5 else ''}")
    print(f"Updated:   {len(result['updated'])} {result['updated']}")
    print(f"Removed:   {len(result['removed'])} {result['removed']}")
    print(f"Unchanged: {result['unchanged']}")
    print(f"Total chunks in index: {result['total_chunks']}")
    print_stats(samples=args.samples)
