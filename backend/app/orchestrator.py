"""
Tool orchestrator: PROMPT-BASED function calling on top of a plain chat model.

  1. route(): a small, separate LLM call whose prompt lists every tool (name, description,
     JSON schema) plus a few examples. The model replies with either NONE or ONE JSON tool call
     {"tool": ..., "arguments": {...}}. It runs IN PARALLEL with the off-topic classifier and
     retrieval (see turn.py), so it adds almost no latency to the turn.
  2. parse_tool_call() validates the JSON; run_tool() runs the tool with
     asyncio.wait_for(timeout=TOOL_TIMEOUT_S). A timeout or error becomes a friendly message.
  3. tool_result_message() is added to the normal prompt as a system message, and the normal
     streaming generation words the final answer (streamed to the chat, spoken in voice mode).

Why a separate router call instead of putting the tools in the main system prompt: measured on
qwen2.5:3b, with the tools buried in the ~1,600-token persona prompt plus retrieved sources, the
model did not emit a tool call for any of 7 tool requests (it answered "please give me your
height" or refused BMI as "math"). With a short prompt whose ONLY job is choosing a tool, it does
(see README / PROMPTS.md). At most ONE tool call per turn: bounded latency, enough for the brief.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from app.llm_engine import LLMEngine
from app.tools import TOOLS
from app.tools.base import ToolContext, ToolError, validate_args

logger = logging.getLogger("zor_assistant")

TOOL_TIMEOUT_S = 5.0
ROUTER_NUM_PREDICT = 120  # enough for the longest JSON call; NONE stops after ~2 tokens
FRIENDLY_TIMEOUT = "The tool took too long to respond."
FRIENDLY_ERROR = "The tool ran into an unexpected problem."


def router_prompt() -> str:
    """System prompt of the router call: the tools, the output format, and examples."""
    tools = "\n".join(
        f"- {t.name}: {t.description}\n  arguments: {json.dumps(t.parameters['properties'], separators=(',', ':'))}"
        f"\n  required: {t.parameters['required']}"
        for t in TOOLS.values()
    )
    return f"""You decide whether the member's LAST message needs one of these tools.

TOOLS:
{tools}

Reply with EXACTLY ONE of:
  NONE                                              (no tool is needed)
  {{"tool": "<tool name>", "arguments": {{...}}}}       (one JSON object, nothing else)

Rules: use only numbers and words the member actually said (earlier messages count); leave out
arguments they did not give -- never guess them. Questions about the gym itself (plans, prices,
classes, trainers, timings, policies) are NONE. Greetings and general chat are NONE.

Examples:
"What's my BMI? I'm 80 kg and 180 cm" -> {{"tool": "calculate_fitness_metrics", "arguments": {{"metric": "bmi", "weight_kg": 80, "height_cm": 180}}}}
"I'm a 30 year old woman, 60 kg, 165 cm, lightly active. How many calories should I eat?" -> {{"tool": "calculate_fitness_metrics", "arguments": {{"metric": "daily_calories", "weight_kg": 60, "height_cm": 165, "age": 30, "sex": "female", "activity_level": "light"}}}}
"I squatted 100 kg for 5 reps, what's my max?" -> {{"tool": "calculate_fitness_metrics", "arguments": {{"metric": "one_rep_max", "lifted_kg": 100, "reps": 5}}}}
"How much protein is in 2 eggs?" -> {{"tool": "lookup_nutrition", "arguments": {{"food": "egg", "servings": 2}}}}
"Calories in 150 grams of rice" -> {{"tool": "lookup_nutrition", "arguments": {{"food": "rice", "grams": 150}}}}
"Add chest day on Tuesday, 45 minutes" -> {{"tool": "workout_schedule", "arguments": {{"action": "add", "day": "Tuesday", "workout": "chest day", "duration_min": 45}}}}
"What workouts do I have this week?" -> {{"tool": "workout_schedule", "arguments": {{"action": "list"}}}}
"Remove my Friday workout" -> {{"tool": "workout_schedule", "arguments": {{"action": "delete", "day": "Friday"}}}}
"My name is Sara and I want to lose weight" -> {{"tool": "user_profile", "arguments": {{"action": "update", "name": "Sara", "fitness_goal": "lose weight"}}}}
"I hurt my left knee last month" -> {{"tool": "user_profile", "arguments": {{"action": "update", "injuries": "left knee hurt last month"}}}}
"I prefer evening classes" -> {{"tool": "user_profile", "arguments": {{"action": "update", "preferences": "evening classes"}}}}
"What do you remember about me?" -> {{"tool": "user_profile", "arguments": {{"action": "get"}}}}
"What is my name?" -> {{"tool": "user_profile", "arguments": {{"action": "get"}}}}
"Tell me my name." -> {{"tool": "user_profile", "arguments": {{"action": "get"}}}}
"No, it's actually Sarah, not Sara" -> {{"tool": "user_profile", "arguments": {{"action": "update", "name": "Sarah"}}}}
"How much is the Elite plan?" -> NONE
"When is the Zumba class?" -> NONE
"What classes do you have on Tuesdays?" -> NONE
"What should I eat after a workout?" -> NONE
"Hi there!" -> NONE"""


def parse_tool_call(text: str) -> dict | None:
    """{"tool": name, "arguments": {...}} if `text` contains a call to a known tool, else None."""
    match = re.search(r"\{.*\}", text, re.DOTALL)  # tolerate ```json fences or a leading word
    if not match:
        return None
    try:
        call = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(call, dict) or call.get("tool") not in TOOLS:
        return None
    arguments = call.get("arguments")
    return {"tool": call["tool"], "arguments": arguments if isinstance(arguments, dict) else {}}


async def route(llm_engine: LLMEngine, recent: list[dict], user_text: str) -> dict | None:
    """The router call. `recent` = the last few history messages (for follow-ups like "and
    for 3 eggs?"). Returns a parsed tool call, or None. Never raises: if the router fails,
    the turn simply continues without a tool."""
    messages = [{"role": "system", "content": router_prompt()}, *recent,
                {"role": "user", "content": user_text}]
    try:
        raw, _ = await llm_engine.generate_with_stats(messages, num_predict=ROUTER_NUM_PREDICT, temperature=0.0)
    except Exception as e:
        logger.warning("Tool router failed (%s); continuing without tools", e)
        return None
    call = parse_tool_call(raw)
    if call is None and "{" in raw:
        logger.warning("Router output was not a valid tool call: %r", raw[:200])
    return call


async def run_tool(name: str, arguments: dict, ctx: ToolContext,
                   timeout: float = TOOL_TIMEOUT_S) -> tuple[bool, dict | str]:
    """Run one tool. Returns (ok, result); never raises."""
    tool = TOOLS[name]
    try:
        args = validate_args(tool.parameters, arguments)
        return True, await asyncio.wait_for(tool.run(args, ctx), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Tool %s timed out after %.1fs", name, timeout)
        return False, FRIENDLY_TIMEOUT
    except ToolError as e:
        return False, str(e)
    except Exception:
        logger.exception("Tool %s crashed", name)
        return False, FRIENDLY_ERROR


def tool_result_message(name: str, ok: bool, result: dict | str) -> str:
    """The system message that hands the tool's result to the main (persona) model."""
    if ok:
        return (f"TOOL RESULT -- the system already ran {name} for the member's latest message: "
                f"{json.dumps(result, ensure_ascii=False)}\nThese values are FINAL and correct: "
                "repeat them exactly as written. They are TOTALS for the whole amount asked (e.g. "
                "all the eggs together), never per item, so don't say 'each'. "
                "Never recalculate or change a number. This request is IN SCOPE (the member's own "
                "fitness), so do not refuse. Answer in 1-3 short, friendly sentences, speaking "
                "directly to the member as if you worked it out yourself -- e.g. \"Two eggs have "
                "about 13 grams of protein.\" -- never say 'the tool', 'the result' or 'the "
                "system'. Don't add any gym facts (classes, times, prices) that are not in the "
                "SOURCES message.")
    return (f"TOOL FAILED -- the system tried {name} for the member's latest message and it "
            f"failed: {result}\nThis request is IN SCOPE. Tell the member kindly, in one or two "
            "sentences, what went wrong or which details you still need. Don't mention JSON.")
