"""
Live multi-turn evaluation through the REAL WebSocket (the same path as the browser).

35 answerable questions (the 20 in test_questions.json + 15 realistic new ones, several of
them "trick" questions whose correct answer is a rule-based "no") are mixed with controls
(BJJ, Lahore, off-topic, small talk) and shuffled into long sessions of 10 messages.
Each run uses a different order (seeded), so every question is asked after different,
unrelated previous messages -- exactly the situation that broke the follow-up rule.

For every reply we record:
  refused  -- the reply says the documents don't cover it / it can't help / off-topic redirect
  correct  -- the expected fact (a regex) is in the reply and it is not a refusal
  sources  -- the optional `sources` field of `done` (citation chips)

Usage (backend running on :8000):
    backend/.venv/Scripts/python.exe eval/live_session_eval.py --runs 3 --label before
"""
import argparse
import asyncio
import json
import random
import re
import sys
from pathlib import Path

import websockets

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent

REFUSAL = re.compile(
    r"don.?t cover|do not cover|doesn.?t cover|not covered|can.?t look that up|outside what I can help|"
    r"outside my|pass on that|my lane is|wheelhouse|outside of what|not something I can help",
    re.IGNORECASE,
)

# The 20 answerable test questions: a regex for a correct answer (alternatives allowed).
ORIGINAL_EXPECT = {
    1: r"16,000", 2: r"8,000|compact", 3: r"waiv|no admission", 4: r"can.?not|can.?t|not be frozen|no freeze",
    5: r"1,500", 6: r"Sana", 7: r"8:00|8 ?am", 8: r"1:00|1 ?pm|2:15", 9: r"9:30|10:00|10 ?am|2:00",
    10: r"6:00|6 ?pm|no guests|not allowed", 11: r"yoga|pilates|not allowed", 12: r"no sauna|steam|doesn.?t have a sauna|not have a sauna",
    13: r"3.{0,4}8|90 minutes|female member", 14: r"18,000", 15: r"50 ?km|relocat|10%", 16: r"25%|4:00|4 ?pm|off-peak",
    17: r"10,000|16,000|12,000", 18: r"Long Ride", 19: r"banana|date|oat|roti|egg|dahi", 20: r"tracksuit|13 months|extra month",
}

NEW_QUESTIONS = [  # (question, regex for a correct answer)
    ("How much is the Plus plan?", r"16,000"),
    ("Can students get a discount?", r"25%|12,000|9,000|6,000"),
    ("What is the guest fee?", r"1,000"),
    ("Is there a pool at F-7?", r"20 ?m|heated|\byes\b|pool (is|session|access)|included|per swim|1,500"),
    ("I'm a student. Can I get 25% off the Elite plan if I train at 8pm?", r"\bno\b|not available|only|Standard|Plus|4:00|4 ?pm|off-peak"),
    ("My friend did a free trial yesterday. Can I bring him as a guest tomorrow?", r"7 days|seven days|\bno\b|can.?t|cannot|not"),
    ("What is the price of the Platinum plan?", r"Standard|Elite|Ladies Only|no Platinum|not have a Platinum|don.?t have a Platinum|doesn.?t have a Platinum|not a plan|not offered|isn.?t a plan"),
    ("Can I freeze my monthly plan?", r"can.?not|can.?t|not be frozen|\bno\b"),
    ("What time does the Bahria Ladies Wing close?", r"9:00|9 ?pm"),
    ("Who teaches Zumba?", r"Farah"),
    ("How much is personal training?", r"18,000"),
    ("Is G-11 open on Sunday?", r"closed|not open|\bno\b"),
    ("What is the late fee for instalments?", r"1,500"),
    ("Do you accept JazzCash?", r"\byes\b|accept|JazzCash"),
    ("Is there a sauna at Bahria?", r"\bno\b|steam|not"),
]

# Controls: behaviour that must NOT change.
CONTROLS = [
    ("Do you offer Brazilian jiu-jitsu or MMA classes?", "bjj"),
    ("Do you have a branch in Lahore or Karachi?", "lahore"),
    ("Who won the cricket World Cup?", "offtopic"),
    ("Write me a Python function to reverse a string.", "offtopic"),
    ("hi", "smalltalk"),
]


def build_items() -> list[dict]:
    data = json.loads((ROOT / "test_questions.json").read_text(encoding="utf-8"))
    items = [{"kind": "answerable", "id": f"T{q['id']}", "q": q["question"], "expect": ORIGINAL_EXPECT[q["id"]]}
             for q in data if q["in_corpus"]]
    items += [{"kind": "answerable", "id": f"N{i + 1}", "q": q, "expect": e} for i, (q, e) in enumerate(NEW_QUESTIONS)]
    items += [{"kind": kind, "id": f"C{i + 1}", "q": q, "expect": None} for i, (q, kind) in enumerate(CONTROLS)]
    return items


async def ask(ws, text: str) -> tuple[str, list | None]:
    await ws.send(json.dumps({"type": "message", "content": text}))
    parts = []
    while True:
        ev = json.loads(await ws.recv())
        if ev["type"] == "token":
            parts.append(ev["content"])
        elif ev["type"] == "done":
            return "".join(parts).strip(), ev.get("sources")
        elif ev["type"] == "error":
            return f"[error] {ev['message']}", None


def control_ok(kind: str, reply: str) -> bool:
    if kind == "bjj":  # must not claim we offer BJJ/MMA: "no" / "not offered" / "don't cover" are all fine
        says_no = re.search(r"\bno\b|not offer|don.?t offer|not available|don.?t cover|doesn.?t cover", reply, re.I)
        claims_yes = re.search(r"(we|zor) (offer|have|run)s? (brazilian|bjj|mma|jiu)", reply, re.I)
        return bool(says_no) and not claims_yes
    if kind == "lahore":
        return not re.search(r"Lahore branch (is|at)|our Lahore|Karachi branch (is|at)", reply, re.I)
    if kind == "offtopic":
        return bool(REFUSAL.search(reply)) and "def " not in reply and "Pakistan won" not in reply
    return True  # small talk: any polite reply


async def run(run_no: int, session_size: int, log: list) -> None:
    items = build_items()
    random.Random(run_no).shuffle(items)
    for start in range(0, len(items), session_size):
        async with websockets.connect("ws://127.0.0.1:8000/ws/chat") as ws:
            await ws.recv()  # session event
            for pos, it in enumerate(items[start:start + session_size]):
                reply, sources = await ask(ws, it["q"])
                refused = bool(REFUSAL.search(reply))
                row = {"run": run_no, "pos": pos, **it, "reply": reply, "sources": sources, "refused": refused}
                if it["kind"] == "answerable":
                    row["correct"] = (not refused) and bool(re.search(it["expect"], reply, re.IGNORECASE))
                else:
                    row["correct"] = control_ok(it["kind"], reply)
                log.append(row)
                mark = "OK " if row["correct"] else ("REF" if refused else "BAD")
                print(f"[run {run_no} s{start // session_size} #{pos}] {mark} {it['id']:>4} {it['q'][:55]!r} -> "
                      f"{reply[:90].replace(chr(10), ' ')!r}  chips={sources}")


def summarize(log: list, label: str) -> str:
    ans = [r for r in log if r["kind"] == "answerable"]
    n = len(ans)
    refused = sum(r["refused"] for r in ans)
    correct = sum(r["correct"] for r in ans)
    lines = [f"## {label}: {n} answerable replies ({len(ans) // max(1, len({r['run'] for r in ans}))} questions x runs)",
             f"- refusal rate on answerable questions: {refused}/{n} = {100 * refused / n:.1f}%",
             f"- correct-answer rate: {correct}/{n} = {100 * correct / n:.1f}%",
             f"- answerable replies with citation chips: {sum(1 for r in ans if r['sources'])}/{n}"]
    for kind in ("bjj", "lahore", "offtopic", "smalltalk"):
        rows = [r for r in log if r["kind"] == kind]
        lines.append(f"- control {kind}: {sum(r['correct'] for r in rows)}/{len(rows)} as expected")
    bad = [r for r in ans if not r["correct"]]
    if bad:
        lines.append("\nFailures:")
        for r in bad:
            lines.append(f"- run {r['run']} {r['id']} {'REFUSED' if r['refused'] else 'WRONG'}: {r['q']!r} -> {r['reply'][:140]!r}")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--session-size", type=int, default=10)
    parser.add_argument("--label", default="run")
    parser.add_argument("--rescore", help="re-score a saved live_session_<label>.json with the current rules")
    args = parser.parse_args()
    if args.rescore:
        log = json.loads((ROOT / f"live_session_{args.rescore}.json").read_text(encoding="utf-8"))
        expect = {it["id"]: it["expect"] for it in build_items()}
        for row in log:
            row["refused"] = bool(REFUSAL.search(row["reply"]))
            if row["kind"] == "answerable":
                row["correct"] = (not row["refused"]) and bool(re.search(expect[row["id"]], row["reply"], re.IGNORECASE))
            else:
                row["correct"] = control_ok(row["kind"], row["reply"])
        print(summarize(log, args.rescore + " (re-scored)"))
        (ROOT / f"live_session_{args.rescore}.md").write_text(summarize(log, args.rescore) + "\n", encoding="utf-8")
        return
    log: list = []
    for r in range(1, args.runs + 1):
        await run(r, args.session_size, log)
    report = summarize(log, args.label)
    print("\n" + report)
    (ROOT / f"live_session_{args.label}.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    (ROOT / f"live_session_{args.label}.md").write_text(report + "\n", encoding="utf-8")


asyncio.run(main())
