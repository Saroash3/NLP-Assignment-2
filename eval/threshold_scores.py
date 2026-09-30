"""
Prints the top-1 similarity score for each test question, split into answerable
vs not-answerable, so the similarity threshold can be chosen from real data.

Usage (from repo root):  backend/.venv/Scripts/python.exe eval/threshold_scores.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from rag.retriever import retrieve  # noqa: E402

questions = json.loads((ROOT / "eval" / "test_questions.json").read_text(encoding="utf-8"))

for answerable in (True, False):
    print("\n== ANSWERABLE ==" if answerable else "\n== NOT ANSWERABLE ==")
    print(f"{'id':>3} {'top1':>6}  {'top-1 source':38} {'hit':4} question")
    for q in (q for q in questions if q["in_corpus"] == answerable):
        top = retrieve(q["question"])
        sources = [c["source"] for c in top]
        # hit = one of the expected source files is anywhere in the top-k
        hit = ("yes" if set(sources) & set(q["expected_sources"]) else "NO") if answerable else "-"
        print(f"{q['id']:>3} {top[0]['score']:>6.3f}  {top[0]['source']:38} {hit:4} {q['question']}")
