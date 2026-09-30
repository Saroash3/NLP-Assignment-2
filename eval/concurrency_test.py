"""
Concurrency test (Phase III): N simultaneous WebSocket clients, each asking a
different question, for N = 5 and N = 10. Reports time to first token (TTFT) and
total time per client. At the same time a probe hits GET /health and
POST /session/new every 250 ms, to show whether the server itself stays
responsive while the clients are waiting on the LLM.

Usage (backend running on :8000):  backend/.venv/Scripts/python.exe eval/concurrency_test.py
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx
import websockets

sys.stdout.reconfigure(encoding="utf-8")
# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first, and uvicorn
# only listens on IPv4, so every new connection would wait ~2 s for the fallback.
BASE = "127.0.0.1:8000"
QUESTIONS = [q["question"] for q in json.loads(
    (Path(__file__).parent / "test_questions.json").read_text(encoding="utf-8")) if q["in_corpus"]]


async def client(i: int, question: str) -> dict:
    async with websockets.connect(f"ws://{BASE}/ws/chat") as ws:
        await ws.recv()  # session event
        t0 = time.perf_counter()  # timed from sending the message, like a user waiting for a reply
        await ws.send(json.dumps({"type": "message", "content": question}))
        first, tokens = None, 0
        while True:
            event = json.loads(await ws.recv())
            if event["type"] == "token":
                first = first or time.perf_counter()
                tokens += 1
            elif event["type"] in ("done", "error"):
                end = time.perf_counter()
                return {"id": i, "q": question, "ttft": first - t0 if first else None,
                        "total": end - t0, "tokens": tokens, "end": event["type"]}


async def probe(stop: asyncio.Event) -> dict:
    """Latency of two cheap endpoints while the clients run."""
    health, session = [], []
    async with httpx.AsyncClient(base_url=f"http://{BASE}", timeout=10) as http:
        while not stop.is_set():
            t = time.perf_counter()
            await http.get("/health")
            health.append(time.perf_counter() - t)
            t = time.perf_counter()
            await http.post("/session/new")
            session.append(time.perf_counter() - t)
            await asyncio.sleep(0.25)
    return {"health": health, "session": session}


async def run(n: int) -> None:
    stop = asyncio.Event()
    probe_task = asyncio.create_task(probe(stop))
    results = await asyncio.gather(*(client(i, QUESTIONS[i % len(QUESTIONS)]) for i in range(n)))
    stop.set()
    probes = await probe_task

    print(f"\n### {n} simultaneous clients\n")
    print("| client | question | TTFT s | total s | tokens | ended with |")
    print("|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda r: r["ttft"] or 1e9):
        ttft = f"{r['ttft']:.2f}" if r["ttft"] else "–"
        print(f"| {r['id']} | {r['q'][:45]} | {ttft} | {r['total']:.2f} | {r['tokens']} | {r['end']} |")
    ttfts = [r["ttft"] for r in results if r["ttft"]]
    print(f"\nTTFT: min {min(ttfts):.2f}s, median {statistics.median(ttfts):.2f}s, max {max(ttfts):.2f}s. "
          f"All {n} done after {max(r['total'] for r in results):.2f}s.")
    for name, values in probes.items():
        print(f"Probe {name}: {len(values)} requests, avg {1000 * statistics.mean(values):.0f} ms, "
              f"max {1000 * max(values):.0f} ms")


async def single_user(repeats: int = 5) -> None:
    """Baseline: one client at a time, `repeats` different questions in sequence."""
    ttfts, totals = [], []
    for i in range(repeats):
        r = await client(i, QUESTIONS[i])
        ttfts.append(r["ttft"])
        totals.append(r["total"])
    print(f"\n### Single user ({repeats} questions, one at a time)\n")
    print(f"TTFT: median {statistics.median(ttfts):.2f}s (min {min(ttfts):.2f}, max {max(ttfts):.2f}); "
          f"total: median {statistics.median(totals):.2f}s")


async def main() -> None:
    await single_user()
    for n in (5, 10):
        await run(n)


asyncio.run(main())
