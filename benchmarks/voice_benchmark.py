"""
Voice latency benchmark (Assignment 3). Talks to the REAL running backend like a browser would:
each question is synthesized with Piper, resampled to 16 kHz, and streamed over /ws/chat as
64 ms binary frames IN REAL TIME, followed by silence, so the VAD ends the utterance exactly as
it would for a person. The server's `latency` event of each turn is collected.

Three scenarios:
  single      one voice user, questions one after another
  voice+text  one voice user and one typing user at the same time
  2 voice     two voice users at the same time

Usage (backend running on :8000, from the repo root):
    backend/.venv/Scripts/python benchmarks/voice_benchmark.py
Writes benchmarks/voice_results.md and prints the same tables.
"""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import websockets

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
sys.stdout.reconfigure(encoding="utf-8")

from app.voice import tts  # noqa: E402  (only to make the spoken test questions)

URL = "ws://127.0.0.1:8000/ws/chat?extended=1"  # 127.0.0.1: avoids Windows' slow IPv6 fallback
FRAME = 1024  # samples per frame = 64 ms at 16 kHz, like the browser's AudioWorklet
QUESTIONS = [
    "What time does the F-7 branch open?",          # RAG
    "How much protein is in two eggs?",             # tool: lookup_nutrition
    "What is my BMI if I weigh 80 kilos and I am 180 centimetres tall?",  # tool: metrics
    "Add leg day on Monday to my workout schedule.",  # tool: workout_schedule
    "How much is the Elite plan?",                  # RAG
    "Hi, how are you today?",                       # small talk
]
TEXT_QUESTIONS = ["What classes do you have on Tuesdays?", "Can I freeze my membership?",
                  "Do you have a pool?", "What is included in the Plus plan?"]
FIELDS = ["asr_ms", "retrieval_ms", "tool_ms", "llm_first_token_ms", "tts_first_audio_ms", "total_ms"]


def speech_16k(text: str) -> np.ndarray:
    pcm = np.frombuffer(tts.synthesize(text), dtype=np.int16).astype(np.float32)
    n = int(len(pcm) * 16000 / tts.sample_rate())
    return np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.int16)


async def stream(ws, audio: np.ndarray) -> None:
    """Send audio + 1.2 s of silence at real-time speed."""
    audio = np.concatenate([np.zeros(3200, np.int16), audio, np.zeros(19200, np.int16)])
    start = time.perf_counter()
    for i in range(0, len(audio), FRAME):
        await ws.send(audio[i:i + FRAME].tobytes())
        await asyncio.sleep(max(0.0, start + (i + FRAME) / 16000 - time.perf_counter()))


async def voice_user(name: str, questions: list[str], clips: dict) -> list[dict]:
    rows = []
    async with websockets.connect(URL + f"&user_id=bench-{name}", max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "voice_start"}))
        await ws.recv()  # listening
        for q in questions:
            sender = asyncio.create_task(stream(ws, clips[q]))
            speech_end = None
            transcript, first_audio, tools = "", None, []
            while True:
                event = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                if event["type"] == "transcript" and event["final"]:
                    transcript = event["text"]
                elif event["type"] == "tool_call":
                    tools.append(event["name"])
                elif event["type"] == "audio" and first_audio is None:
                    first_audio = time.perf_counter()
                elif event["type"] == "latency":
                    break
                elif event["type"] == "error":
                    print(f"  [{name}] error: {event}")
            await sender
            rows.append({"user": name, "question": q, "transcript": transcript,
                         "tools": ",".join(tools) or "-", **{f: event.get(f) for f in FIELDS}})
            await ws.recv()  # voice_state listening (next turn)
    return rows


async def text_user(questions: list[str]) -> list[dict]:
    rows = []
    async with websockets.connect(URL + "&user_id=bench-text") as ws:
        await ws.recv()
        for q in questions:
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "message", "content": q}))
            first = None
            while True:
                event = json.loads(await ws.recv())
                if event["type"] == "token" and first is None:
                    first = time.perf_counter()
                if event["type"] in ("latency", "error"):
                    break
            rows.append({"question": q, "first_token_ms": round((first - t0) * 1000) if first else None})
    return rows


def table(rows: list[dict]) -> str:
    head = "| User | Question (spoken) | Transcript | Tool | ASR | Retrieval+routing | Tool | LLM 1st token | TTS 1st audio | **End-of-speech → 1st audio** |"
    lines = [head, "|" + "---|" * 10]
    for r in rows:
        cells = [r["user"], r["question"], r["transcript"], r["tools"]] + [
            "-" if r[f] is None else f"{r[f]:.0f}" for f in FIELDS]
        cells[-1] = f"**{cells[-1]}**"
        lines.append("| " + " | ".join(cells) + " |")
    totals = [r["total_ms"] for r in rows if r["total_ms"] is not None]
    if totals:
        lines.append(f"\nEnd-of-speech → first audio (ms): median **{statistics.median(totals):.0f}**, "
                     f"max {max(totals):.0f}, n={len(totals)}.")
    return "\n".join(lines)


async def main() -> None:
    tts.load()
    clips = {q: speech_16k(q) for q in QUESTIONS}
    out = ["# Voice latency benchmark", "",
           "All times in ms, measured by the server per voice turn (`latency` event). "
           "\"End of speech\" = the moment the VAD decides the member stopped talking, which is "
           "0.5 s of silence after the last word (that hangover is not included).", ""]

    print("Scenario 1: single voice user")
    single = await voice_user("A", QUESTIONS, clips)
    out += ["## 1. One voice user", "", table(single), ""]

    print("Scenario 2: voice user + text user at the same time")
    voice_rows, text_rows = await asyncio.gather(voice_user("A", QUESTIONS[:4], clips), text_user(TEXT_QUESTIONS))
    out += ["## 2. One voice user + one text user concurrently", "", table(voice_rows), "",
            "Text user (same time), time to first token: " +
            ", ".join(f"{r['first_token_ms']} ms" for r in text_rows), ""]

    print("Scenario 3: two voice users at the same time")
    a, b = await asyncio.gather(voice_user("A", QUESTIONS[:3], clips), voice_user("B", QUESTIONS[3:], clips))
    out += ["## 3. Two voice users concurrently", "", table(a + b), ""]

    report = "\n".join(out)
    print(report)
    (Path(__file__).parent / "voice_results.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
