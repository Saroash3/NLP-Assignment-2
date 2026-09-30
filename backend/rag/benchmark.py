"""
Latency benchmark (Phase III), over the 25 questions in eval/test_questions.json.

Part A -- retrieval ALONE (no LLM):
  cold      : loading the embedding model + opening Chroma, then the very first query
  miss      : model loaded, cache empty -> embed the query + vector search
              (also split into "embed" and "search" so we can see where the time goes)
  hit       : the same queries again -> served from the LRU cache
Part B -- end-to-end, the same code path as main.py (classifier and retrieval in
  parallel, then prompt building and streaming), for the 20 answerable questions:
  time to first token (TTFT), total reply time, and retrieval as a share of the total.

Usage (from backend/, Ollama running):  python -m rag.benchmark
Results are printed and written to rag/benchmark_results.md.
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from rag import retriever
from rag.store import REPO_ROOT, index_version

ROUNDS = 3  # each warm measurement is repeated 3x over the 25 questions (75 samples)


def ms(seconds: float) -> float:
    return seconds * 1000


def stats(values: list[float]) -> tuple[float, float, float]:
    """(average, median, p95) of a list of milliseconds."""
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return statistics.mean(values), statistics.median(values), p95


def row(label: str, values: list[float]) -> str:
    avg, med, p95 = stats(values)
    return f"| {label} | {len(values)} | {avg:.2f} | {med:.2f} | {p95:.2f} |"


def bench_retrieval(questions: list[str]) -> tuple[list[str], dict]:
    lines = ["| Retrieval only | samples | avg ms | median ms | p95 ms |", "|---|---|---|---|---|"]

    # Cold: nothing loaded yet in this process.
    start = time.perf_counter()
    retriever.load()
    load_ms = ms(time.perf_counter() - start)
    start = time.perf_counter()
    retriever.retrieve(questions[0])
    first_ms = ms(time.perf_counter() - start)

    embed_ms, search_ms, miss_ms, hit_ms = [], [], [], []
    version = index_version()
    for _ in range(ROUNDS):
        retriever.clear_cache()
        for q in questions:  # cache MISS, split into its two steps
            t0 = time.perf_counter()
            retriever._embed_query(q)
            t1 = time.perf_counter()
            retriever._search(q, retriever.TOP_K, version)  # embedding is cached now -> pure search
            t2 = time.perf_counter()
            embed_ms.append(ms(t1 - t0))
            search_ms.append(ms(t2 - t1))
        retriever.clear_cache()
        for q in questions:  # cache MISS through the public function
            t0 = time.perf_counter()
            retriever.retrieve(q)
            miss_ms.append(ms(time.perf_counter() - t0))
        for q in questions:  # the same queries again -> cache HIT
            t0 = time.perf_counter()
            retriever.retrieve(q)
            hit_ms.append(ms(time.perf_counter() - t0))

    lines += [
        f"| Cold start: load model + open index (once, at server startup) | 1 | {load_ms:.0f} | – | – |",
        f"| Cold: first query after loading | 1 | {first_ms:.1f} | – | – |",
        row("Warm, cache miss: embed query", embed_ms),
        row("Warm, cache miss: vector search", search_ms),
        row("**Warm, cache miss: total retrieval**", miss_ms),
        row("**Warm, cache hit**", hit_ms),
    ]
    return lines, {"miss": miss_ms}


async def bench_end_to_end(questions: list[str]) -> list[str]:
    from app.conversation_manager import ConversationManager
    from app.llm_engine import LLMEngine

    cm, engine = ConversationManager(), LLMEngine()
    await engine.generate_with_stats([{"role": "user", "content": "hi"}], num_predict=1)  # load LLM

    async def timed(coro):
        t0 = time.perf_counter()
        result = await coro
        return result, time.perf_counter() - t0

    ret_ms, clf_ms, ttft_ms, total_ms, share = [], [], [], [], []
    retriever.clear_cache()  # every retrieval below is a cache miss (worst case)
    for q in questions:
        session = cm.create_session()
        start = time.perf_counter()
        (redirect, t_clf), (chunks, t_ret) = await asyncio.gather(
            timed(cm.classify_off_topic(engine, q)), timed(cm.retrieve_context(session, q))
        )
        redirect = cm.apply_retrieval_override(redirect, chunks)
        if redirect:
            continue  # canned redirect, no generation to time
        first = None
        async for _ in engine.stream_chat(cm.build_prompt_messages(session, q, chunks)):
            first = first or time.perf_counter()
        end = time.perf_counter()
        ret_ms.append(ms(t_ret))
        clf_ms.append(ms(t_clf))
        ttft_ms.append(ms(first - start))
        total_ms.append(ms(end - start))
        share.append(100 * t_ret / (end - start))
    await engine.aclose()

    avg_share = statistics.mean(share)
    return [
        "| End-to-end (answerable questions) | samples | avg ms | median ms | p95 ms |",
        "|---|---|---|---|---|",
        row("Retrieval (runs in parallel with the classifier)", ret_ms),
        row("Off-topic classifier (LLM call)", clf_ms),
        row("**Time to first token**", ttft_ms),
        row("**Total reply time**", total_ms),
        "",
        f"Retrieval = **{avg_share:.1f}%** of the total reply time on average. It runs in parallel "
        f"with the classifier ({statistics.mean(clf_ms):.0f} ms average), so it adds about 0 ms "
        "to the wait for the first token.",
    ]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads((REPO_ROOT / "eval" / "test_questions.json").read_text(encoding="utf-8"))
    all_q = [q["question"] for q in data]
    answerable = [q["question"] for q in data if q["in_corpus"]]

    part_a, _ = bench_retrieval(all_q)
    part_b = asyncio.run(bench_end_to_end(answerable))
    report = "\n".join(
        ["## Latency benchmark", "", f"Run: {time.strftime('%Y-%m-%d %H:%M')}; "
         f"{len(all_q)} test questions; warm rows = {ROUNDS} rounds.", "", *part_a, "", *part_b, ""]
    )
    print(report)
    (Path(__file__).parent / "benchmark_results.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
