"""
End-to-end examples through the REAL WebSocket endpoint (same protocol as the
frontend). Each inner list is one conversation (one session), so follow-ups
work. Retrieved sources for each turn are printed by the server log
("Retrieval ... -> [(source, score), ...]").

Usage (backend running on :8000):  backend/.venv/Scripts/python.exe eval/e2e_examples.py
"""
import asyncio
import json
import sys
import time

import websockets

sys.stdout.reconfigure(encoding="utf-8")

CONVERSATIONS = [
    ["How much is the Plus membership per month?"],
    ["What are the timings at the Bahria branch?", "and for ladies?"],  # follow-up
    ["Do you have a CrossFit box with a rig?"],  # no-match: classifier ON, top score 0.336 < 0.35
    ["Do you offer Brazilian jiu-jitsu or MMA classes?"],  # gym-adjacent, not covered
    ["Can I bring a guest to G-11 on a weekday evening?"],
]


async def ask(ws, text: str) -> tuple[str, float, list | None]:
    await ws.send(json.dumps({"type": "message", "content": text}))
    start, first, reply = time.perf_counter(), None, []
    while True:
        event = json.loads(await ws.recv())
        if event["type"] == "token":
            first = first or time.perf_counter()
            reply.append(event["content"])
        elif event["type"] in ("done", "error"):
            if event["type"] == "error":
                reply.append(f"[ERROR {event['code']}: {event['message']}]")
            # `sources` = the optional citations field on `done` (absent if not grounded)
            return "".join(reply).strip(), (first or time.perf_counter()) - start, event.get("sources")


async def main() -> None:
    for conversation in CONVERSATIONS:
        async with websockets.connect("ws://127.0.0.1:8000/ws/chat") as ws:
            await ws.recv()  # the initial "session" event
            for text in conversation:
                reply, ttft, sources = await ask(ws, text)
                print(f"\nUSER: {text}\nNOVA ({ttft:.2f}s to first token): {reply}")
                print(f"CITATION CHIPS: {sources if sources else '(none)'}")
        print("-" * 70)


asyncio.run(main())
