"""
Off-topic classification battery (Phase VI). A FIXED, comprehensive set of 30
test messages across three categories, run once against the real two-stage
pipeline (ConversationManager.classify_off_topic) -- replacing one-off manual
probing in the browser with a single, repeatable, measured result.

Categories:
  - on_topic:  clearly in-scope (classes, plans, trainers, bookings, hours,
               location, facilities/amenities)
  - off_topic: clearly out-of-scope (trivia, other domains, coding, math,
               celebrities, news)
  - ambiguous: genuinely borderline cases a real gym receptionist might
               reasonably field (small talk, hours-adjacent questions,
               things not explicitly in the knowledge base but plausibly
               gym-related). These `expected` labels are a judgment call,
               not objective ground truth -- see the `note` on each case for
               the reasoning, and read the pass rate accordingly.

Reuses the real ConversationManager + LLMEngine (same as
benchmarks/benchmark.py), so this measures actual production code, not a
reimplementation of the classifier logic.

Usage (from repo root, with the backend venv active and Ollama running):
    python evaluation/off_topic_battery.py

Prints a report to stdout and appends it to evaluation/results.md.
"""
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Make the backend's `app` package importable without installing it as a dependency.
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.conversation_manager import ConversationManager  # noqa: E402
from app.llm_engine import LLMEngine  # noqa: E402


@dataclass(frozen=True)
class TestCase:
    text: str
    category: str  # "on_topic" | "off_topic" | "ambiguous"
    expected: str  # "ON_TOPIC" | "OFF_TOPIC"
    note: str = ""


TEST_CASES: list[TestCase] = [
    # --- Clearly on-topic: classes, plans, trainers, bookings, hours, location, facilities ---
    TestCase("What classes do you have on Tuesdays?", "on_topic", "ON_TOPIC"),
    TestCase(
        "What's the difference between the Premium and Elite membership plans?",
        "on_topic",
        "ON_TOPIC",
    ),
    TestCase("Can you tell me about Maya Chen and what she teaches?", "on_topic", "ON_TOPIC"),
    TestCase("I'd like to book the HIIT Blast class this week", "on_topic", "ON_TOPIC"),
    TestCase("What are your opening hours?", "on_topic", "ON_TOPIC"),
    TestCase("Where is Apex Fitness Club located?", "on_topic", "ON_TOPIC"),
    TestCase("Do you have a swimming pool?", "on_topic", "ON_TOPIC"),
    TestCase("What's your policy on freezing a membership?", "on_topic", "ON_TOPIC"),
    TestCase("Can I bring a guest with me?", "on_topic", "ON_TOPIC"),
    TestCase("I'd like to book a free trial session", "on_topic", "ON_TOPIC"),
    # --- Clearly off-topic: trivia, other domains, coding, math, celebrities, news ---
    TestCase("Who is John Cena?", "off_topic", "OFF_TOPIC"),
    TestCase("Who is Taylor Swift?", "off_topic", "OFF_TOPIC"),
    TestCase("When is the next FIFA World Cup?", "off_topic", "OFF_TOPIC"),
    TestCase("What's 45 times 12?", "off_topic", "OFF_TOPIC"),
    TestCase("Write me a JavaScript function to reverse a string", "off_topic", "OFF_TOPIC"),
    TestCase("What's the capital of Australia?", "off_topic", "OFF_TOPIC"),
    TestCase("Can you recommend a good Italian restaurant nearby?", "off_topic", "OFF_TOPIC"),
    TestCase("What stock should I invest in right now?", "off_topic", "OFF_TOPIC"),
    TestCase("Can you help me with my calculus homework?", "off_topic", "OFF_TOPIC"),
    TestCase("What's the latest news on the stock market?", "off_topic", "OFF_TOPIC"),
    # --- Ambiguous / borderline: judgment calls, not objective ground truth ---
    TestCase(
        "Is the gym open on public holidays?", "ambiguous", "ON_TOPIC", "hours-adjacent"
    ),
    TestCase(
        "How's your day going?",
        "ambiguous",
        "ON_TOPIC",
        "small talk a warm front-desk persona should engage with briefly",
    ),
    TestCase(
        "What's the Wi-Fi password?", "ambiguous", "ON_TOPIC", "plausible facility-amenity question"
    ),
    TestCase(
        "Can I leave my bike locked up outside?",
        "ambiguous",
        "ON_TOPIC",
        "facility/policy-adjacent",
    ),
    TestCase(
        "Do you sell protein powder or supplements?",
        "ambiguous",
        "ON_TOPIC",
        "gym-adjacent retail question",
    ),
    TestCase(
        "Is Apex Fitness Club hiring right now?",
        "ambiguous",
        "ON_TOPIC",
        "about the business itself, not an external topic",
    ),
    TestCase(
        "Can you recommend a good hotel nearby?",
        "ambiguous",
        "OFF_TOPIC",
        "asking for an unrelated local recommendation, not gym-related",
    ),
    TestCase(
        "Can I get a receipt for my last payment?", "ambiguous", "ON_TOPIC", "billing/policy-adjacent"
    ),
    TestCase(
        "What's a good pre-workout meal?", "ambiguous", "ON_TOPIC", "general fitness/nutrition question"
    ),
    TestCase(
        "Do you offer childcare while I work out?",
        "ambiguous",
        "ON_TOPIC",
        "facility-adjacent, even though not in the current knowledge base",
    ),
]

CATEGORY_LABELS = {
    "on_topic": "Clearly on-topic",
    "off_topic": "Clearly off-topic",
    "ambiguous": "Ambiguous / borderline (judgment calls -- see notes)",
}


async def run_battery() -> list[dict]:
    engine = LLMEngine()
    conversation_manager = ConversationManager()

    if not await engine.check_health():
        settings = get_settings()
        print(f"ERROR: could not reach Ollama at {settings.ollama_host}.")
        print("Is `ollama serve` running, and has the model been pulled?")
        print(f"  ollama pull {settings.model_name}")
        await engine.aclose()
        sys.exit(1)

    results = []
    for i, case in enumerate(TEST_CASES, start=1):
        redirect = await conversation_manager.classify_off_topic(engine, case.text)
        actual = "OFF_TOPIC" if redirect is not None else "ON_TOPIC"
        passed = actual == case.expected
        mark = "PASS" if passed else "FAIL"
        print(
            f"[{i}/{len(TEST_CASES)}] {mark} ({case.category}) {case.text!r} -> {actual} "
            f"(expected {case.expected})"
        )
        results.append(
            {
                "text": case.text,
                "category": case.category,
                "expected": case.expected,
                "actual": actual,
                "passed": passed,
                "note": case.note,
            }
        )

    await engine.aclose()
    return results


def render_report(results: list[dict]) -> str:
    settings = get_settings()
    lines = [
        f"### Off-topic battery run -- {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Model: `{settings.model_name}` via Ollama at `{settings.ollama_host}`",
        "",
    ]

    overall_pass = 0
    overall_total = 0

    for category in ("on_topic", "off_topic", "ambiguous"):
        cat_results = [r for r in results if r["category"] == category]
        cat_pass = sum(1 for r in cat_results if r["passed"])
        cat_total = len(cat_results)
        overall_pass += cat_pass
        overall_total += cat_total
        pct = (cat_pass / cat_total * 100) if cat_total else 0.0

        lines.append(f"#### {CATEGORY_LABELS[category]}: {cat_pass}/{cat_total} ({pct:.0f}%)")
        lines.append("")
        lines.append("| Message | Expected | Actual | Result | Note |")
        lines.append("|---|---|---|:---:|---|")
        for r in cat_results:
            mark = "PASS" if r["passed"] else "**FAIL**"
            lines.append(f"| {r['text']} | {r['expected']} | {r['actual']} | {mark} | {r['note']} |")
        lines.append("")

    overall_pct = (overall_pass / overall_total * 100) if overall_total else 0.0
    lines.append(f"**Overall: {overall_pass}/{overall_total} ({overall_pct:.0f}%)**")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    results = asyncio.run(run_battery())
    report = render_report(results)
    print("\n" + report)

    results_path = Path(__file__).resolve().parent / "results.md"
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(report)
    print(f"Appended results to {results_path}")


if __name__ == "__main__":
    main()
