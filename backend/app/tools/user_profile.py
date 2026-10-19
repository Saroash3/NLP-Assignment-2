"""
Tool (CRM bonus): user_profile -- remembers the member across sessions, keyed by user ID, in
backend/data/profiles.json:
  {user_id: {name, fitness_goal, injuries, preferences, last_workout,
             interactions: [{at, request}, ...last 5], updated_at}}

Two ways the profile is used:
  1. The LLM calls the tool (via the router) to SAVE facts ("my name is Sara", "I hurt my knee")
     or to READ them ("what do you remember about me?").
  2. The server itself, without the LLM: profile_note() adds the profile to every prompt,
     record_interaction() logs each request, and greeting() welcomes a returning member by name
     and recalls their last request.
"""
from __future__ import annotations

import time
from pathlib import Path

from app.tools.base import Tool, ToolContext, ToolError
from app.tools.json_store import JsonStore

store = JsonStore(Path(__file__).resolve().parents[2] / "data" / "profiles.json")

FIELDS = ["name", "fitness_goal", "injuries", "preferences", "last_workout"]
MAX_INTERACTIONS = 5

PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["get", "update"]},
        "name": {"type": "string", "description": "the member's first name"},
        "fitness_goal": {"type": "string", "description": "e.g. 'lose 5 kg', 'build muscle'"},
        "injuries": {"type": "string", "description": "e.g. 'left knee pain'"},
        "preferences": {"type": "string", "description": "e.g. 'morning classes, vegetarian'"},
        "last_workout": {"type": "string", "description": "e.g. 'legs on Monday'"},
    },
    "required": ["action"],
}


async def run(args: dict, ctx: ToolContext) -> dict:
    if args["action"] == "get":
        profile = await store.get(ctx.user_id) or {}
        known = {k: profile[k] for k in FIELDS if profile.get(k)}
        return {"profile": known or "nothing saved yet"}

    changes = {k: args[k].strip() for k in FIELDS if k in args}
    if not changes:
        raise ToolError("Tell me what to remember: name, goal, injuries, preferences or last workout.")

    def update(data: dict) -> dict:
        profile = data.setdefault(ctx.user_id, {})
        profile.update(changes, updated_at=time.strftime("%Y-%m-%d %H:%M"))
        return {k: profile[k] for k in FIELDS if profile.get(k)}

    return {"saved": changes, "profile": await store.update(update)}


TOOL = Tool(
    name="user_profile",
    description="Remember (update) or recall (get) facts about the member across visits: their "
    "name, fitness goal, injuries, preferences and last workout.",
    parameters=PARAMETERS,
    run=run,
)


# --- Used by the server directly (not LLM tools) ---

async def load(user_id: str) -> dict:
    return await store.get(user_id) or {}


async def record_interaction(user_id: str, request: str) -> None:
    """Log the member's request (last MAX_INTERACTIONS kept) -- 'past interactions'."""
    def append(data: dict) -> None:
        profile = data.setdefault(user_id, {})
        log = profile.setdefault("interactions", [])
        log.append({"at": time.strftime("%Y-%m-%d %H:%M"), "request": request[:200]})
        del log[:-MAX_INTERACTIONS]

    await store.update(append)


def profile_note(profile: dict) -> str | None:
    """System message for the prompt, or None if nothing is known yet."""
    facts = [f"{k.replace('_', ' ')}: {profile[k]}" for k in FIELDS if profile.get(k)]
    past = [i["request"] for i in profile.get("interactions", [])[-3:]]
    if not facts and not past:
        return None
    lines = ["MEMBER PROFILE (remembered from earlier conversations; use it naturally, e.g. call "
             "them by name -- don't read it out unless asked). If an injury is listed, any exercise "
             "advice must avoid stressing it and suggest checking with a trainer or physio:"]
    lines += [f"- {fact}" for fact in facts]
    if past:
        lines.append("- recent requests: " + " | ".join(past))
    return "\n".join(lines)


def greeting(profile: dict) -> str | None:
    """Welcome-back message for a returning member, or None for a new one."""
    name = profile.get("name")
    if not name:
        return None
    interactions = profile.get("interactions", [])
    if interactions:
        return (f"Welcome back, {name}! Last time you asked: \"{interactions[-1]['request']}\". "
                "Want to pick up from there, or is there something new I can help with?")
    return f"Welcome back, {name}! How can I help you today?"
