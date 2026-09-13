"""
Latency benchmark (Phase II/VI). Sends a handful of representative gym
front-desk prompts to the configured local model and measures:
  - time to first token (TTFT)
  - tokens/second during generation
  - total response time

Deliberately reuses the real app.llm_engine.LLMEngine and
app.conversation_manager.ConversationManager -- the exact same code path
the live server uses -- rather than a separate one-off HTTP client, so
these numbers reflect production behavior, not a toy benchmark harness.
Prompts are sent as successive turns in one growing session, so later
prompts reflect realistic prompt sizes (system prompt + accumulated
history), not just an empty first turn every time.

Usage (from repo root, with the backend venv active):
    python benchmarks/benchmark.py

Results print to stdout as a table and are appended to
benchmarks/results.md.
"""
import asyncio
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the backend's `app` package importable without installing it as a dependency.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.conversation_manager import (  # noqa: E402
    CLASSIFIER_NUM_PREDICT,
    CLASSIFIER_TEMPERATURE,
    ConversationManager,
)
from app.llm_engine import LLMEngine, LLMEngineError  # noqa: E402
from app.prompts import build_classification_messages  # noqa: E402

TEST_PROMPTS = [
    "Hi! What are your opening hours?",
    "What's the difference between the Premium and Elite membership plans?",
    "Can you tell me about Maya Chen and what classes she teaches?",
    "I'd like to book the HIIT Blast class this week -- what times is it offered?",
    "What's your policy on freezing a membership?",
]

# A mix of on-topic and off-topic messages, to benchmark Stage 1 of the two-stage
# off-topic pipeline (ConversationManager.classify_off_topic) in isolation. This
# call runs before EVERY message, on-topic or off-topic, so its cost is paid by
# the whole system, not just the off-topic path.
CLASSIFICATION_TEST_MESSAGES = [
    ("What classes do you have on Tuesdays?", "on_topic"),
    ("Who is Taylor Swift?", "off_topic"),
    ("Can you write me a JavaScript function?", "off_topic"),
    ("What's a good high-protein snack after a workout?", "on_topic"),
]


async def run_benchmark(engine: LLMEngine) -> list[dict]:
    conversation_manager = ConversationManager()
    session = conversation_manager.create_session()

    results = []
    for i, prompt in enumerate(TEST_PROMPTS, start=1):
        messages = conversation_manager.build_prompt_messages(session, prompt)
        print(f"[{i}/{len(TEST_PROMPTS)}] Prompting: {prompt!r}")
        try:
            reply, stats = await engine.generate_with_stats(messages)
        except LLMEngineError as e:
            print(f"  ERROR: {e}")
            continue
        conversation_manager.record_turn(session, prompt, reply)

        print(
            f"  TTFT: {stats.time_to_first_token_s:.3f}s | "
            f"tokens/s: {stats.tokens_per_second:.1f} | "
            f"total: {stats.total_time_s:.3f}s | "
            f"completion tokens: {stats.completion_tokens}"
        )
        results.append(
            {
                "prompt": prompt,
                "ttft_s": stats.time_to_first_token_s,
                "tokens_per_second": stats.tokens_per_second,
                "total_time_s": stats.total_time_s,
                "completion_tokens": stats.completion_tokens,
            }
        )

    return results


async def run_classification_benchmark(engine: LLMEngine) -> list[dict]:
    """
    Benchmarks Stage 1 of the two-stage off-topic pipeline (see
    ConversationManager.classify_off_topic) in isolation: a short, separate
    system prompt + a tiny num_predict, so this should be fast in absolute
    terms -- but it runs before EVERY message, on-topic or off-topic, so its
    cost is paid by the whole system, not just off-topic replies.
    """
    results = []
    for text, expected in CLASSIFICATION_TEST_MESSAGES:
        messages = build_classification_messages(text)
        verdict, stats = await engine.generate_with_stats(
            messages, num_predict=CLASSIFIER_NUM_PREDICT, temperature=CLASSIFIER_TEMPERATURE
        )
        results.append(
            {
                "prompt": text,
                "expected": expected,
                "verdict": verdict.strip(),
                "ttft_s": stats.time_to_first_token_s,
                "total_time_s": stats.total_time_s,
                "tokens_per_second": stats.tokens_per_second,
            }
        )
    return results


def render_markdown_table(results: list[dict]) -> str:
    settings = get_settings()
    lines = [
        f"### Benchmark run -- {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Model: `{settings.model_name}` via Ollama at `{settings.ollama_host}`",
        "",
        "| # | Prompt | TTFT (s) | Tokens/s | Total time (s) | Completion tokens |",
        "|---|--------|---------:|---------:|----------------:|-------------------:|",
    ]
    for i, r in enumerate(results, start=1):
        prompt_preview = r["prompt"] if len(r["prompt"]) <= 60 else r["prompt"][:57] + "..."
        lines.append(
            f"| {i} | {prompt_preview} | {r['ttft_s']:.3f} | {r['tokens_per_second']:.1f} "
            f"| {r['total_time_s']:.3f} | {r['completion_tokens']} |"
        )

    if results:
        avg_ttft = statistics.mean(r["ttft_s"] for r in results)
        avg_tps = statistics.mean(r["tokens_per_second"] for r in results)
        avg_total = statistics.mean(r["total_time_s"] for r in results)
        lines.append("")
        lines.append(
            f"**Averages:** TTFT {avg_ttft:.3f}s | {avg_tps:.1f} tokens/s | "
            f"total {avg_total:.3f}s"
        )
    lines.append("")
    return "\n".join(lines)


def render_classification_table(results: list[dict], main_avg_total_s: float | None) -> str:
    """Renders the Stage-1 classification benchmark plus what it adds to overall latency."""
    lines = [
        "### Off-topic classification gate (Stage 1 of the two-stage pipeline)",
        "",
        "Runs before every message, on-topic or off-topic -- see "
        "`ConversationManager.classify_off_topic` and the README's "
        '"Off-topic detection: two-stage pipeline" section.',
        "",
        "| Prompt | Expected | Verdict | Correct? | TTFT (s) | Total time (s) |",
        "|--------|----------|---------|:--------:|---------:|----------------:|",
    ]
    for r in results:
        correct = "yes" if r["expected"].upper() in r["verdict"].upper() else "no"
        prompt_preview = r["prompt"] if len(r["prompt"]) <= 45 else r["prompt"][:42] + "..."
        lines.append(
            f"| {prompt_preview} | {r['expected']} | {r['verdict']} | {correct} "
            f"| {r['ttft_s']:.3f} | {r['total_time_s']:.3f} |"
        )

    if results:
        avg_total = statistics.mean(r["total_time_s"] for r in results)
        lines.append("")
        lines.append(f"**Average classification call: {avg_total:.3f}s.**")
        lines.append("")

        if main_avg_total_s:
            lines.append(
                f"**Off-topic messages: faster than before.** They now finish in roughly this "
                f"~{avg_total:.2f}s classification call alone, instead of a full "
                f"~{main_avg_total_s:.2f}s generation -- the expensive main call is skipped "
                f"entirely."
            )
            added_pct = avg_total / main_avg_total_s * 100
            lines.append(
                f"**On-topic messages: pay this cost on top of the main table's numbers.** "
                f"Roughly +{avg_total:.2f}s ({added_pct:.0f}% of the main call's own total "
                f"time) added on top."
            )
        else:
            lines.append(
                f"**Off-topic messages: faster than before.** Main generation is skipped "
                f"entirely; they now cost roughly this ~{avg_total:.2f}s classification call "
                f"alone."
            )
            lines.append(
                f"**On-topic messages: pay this cost on top of normal generation time.** "
                f"Roughly +{avg_total:.2f}s added on top."
            )
    lines.append("")
    return "\n".join(lines)


async def run_all() -> tuple[list[dict], list[dict]]:
    engine = LLMEngine()
    if not await engine.check_health():
        settings = get_settings()
        print(f"ERROR: could not reach Ollama at {settings.ollama_host}.")
        print("Is `ollama serve` running, and has the model been pulled?")
        print(f"  ollama pull {settings.model_name}")
        await engine.aclose()
        sys.exit(1)

    main_results = await run_benchmark(engine)
    print()
    print("Benchmarking the off-topic classification gate (Stage 1)...")
    classification_results = await run_classification_benchmark(engine)
    for r in classification_results:
        correct = "OK" if r["expected"].upper() in r["verdict"].upper() else "WRONG"
        print(
            f"  [{correct}] {r['prompt']!r} -> {r['verdict']} "
            f"(expected {r['expected']}) | total: {r['total_time_s']:.3f}s"
        )

    await engine.aclose()
    return main_results, classification_results


def main() -> None:
    main_results, classification_results = asyncio.run(run_all())

    main_report = render_markdown_table(main_results)
    main_avg_total_s = (
        statistics.mean(r["total_time_s"] for r in main_results) if main_results else None
    )
    classification_report = render_classification_table(classification_results, main_avg_total_s)

    print("\n" + main_report)
    print(classification_report)

    results_path = Path(__file__).resolve().parent / "results.md"
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(main_report)
        f.write(classification_report)
    print(f"Appended results to {results_path}")


if __name__ == "__main__":
    main()
