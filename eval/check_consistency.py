"""
Consistency check for the document collection (Phase 0).

Every money amount and every clock time written in documents/*.md must also
appear in facts_source_of_truth.md. This catches typos like "PKR 16,500"
when the real price is 16,000. It doesn't prove a document is correct, but
it catches the most common kind of drift.

Usage (from repo root):  python eval/check_consistency.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FACTS = (ROOT / "facts_source_of_truth.md").read_text(encoding="utf-8")

# Numbers with a thousands separator (12,000) and clock times (7:00).
AMOUNT = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")

facts_values = set(AMOUNT.findall(FACTS)) | set(TIME.findall(FACTS))

MIN_WORDS, MAX_WORDS = 250, 500

problems = 0
docs = sorted((ROOT / "documents").glob("*.md"))
for doc in docs:
    text = doc.read_text(encoding="utf-8")
    unknown = sorted(set(AMOUNT.findall(text) + TIME.findall(text)) - facts_values)
    words = len(text.split())
    if unknown:
        problems += 1
        print(f"{doc.name}: not in facts file -> {', '.join(unknown)}")
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems += 1
        print(f"{doc.name}: {words} words (expected {MIN_WORDS}-{MAX_WORDS})")

print(f"\nChecked {len(docs)} documents, {problems} with unknown values.")
sys.exit(1 if problems else 0)
