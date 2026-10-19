"""
Tool: workout_schedule -- add, list or delete the member's planned workouts, saved in
backend/data/workouts.json as {user_id: [workout, ...]}.

The user_id comes from ToolContext (set by the orchestrator), never from the LLM's arguments,
so the model cannot read or edit another member's schedule.
"""
from __future__ import annotations

from pathlib import Path

from app.tools.base import Tool, ToolContext, ToolError
from app.tools.json_store import JsonStore

store = JsonStore(Path(__file__).resolve().parents[2] / "data" / "workouts.json")

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add", "list", "delete"]},
        "day": {"type": "string", "description": "day of the week, e.g. 'Monday' (add; optional for list/delete)"},
        "workout": {"type": "string", "description": "what to do, e.g. 'leg day' or '5 km run' (add)"},
        "duration_min": {"type": "integer", "description": "length in minutes (add, optional)"},
        "workout_id": {"type": "integer", "description": "id of the workout to delete (delete)"},
    },
    "required": ["action"],
}


def _normalize_day(day: str) -> str:
    key = day.strip().lower()
    for full in DAYS:
        if key.startswith(full[:3]):
            return full.capitalize()
    raise ToolError(f"'{day}' is not a day of the week.")


async def run(args: dict, ctx: ToolContext) -> dict:
    action = args["action"]
    day = _normalize_day(args["day"]) if "day" in args else None

    if action == "add":
        if day is None or "workout" not in args:
            raise ToolError("To add a workout I need the day and the workout.")

        def add(data: dict) -> dict:
            workouts = data.setdefault(ctx.user_id, [])
            entry = {"id": max((w["id"] for w in workouts), default=0) + 1, "day": day,
                     "workout": args["workout"], "duration_min": args.get("duration_min")}
            workouts.append(entry)
            return entry

        return {"added": await store.update(add)}

    if action == "list":
        workouts = await store.get(ctx.user_id) or []
        if day:
            workouts = [w for w in workouts if w["day"] == day]
        workouts.sort(key=lambda w: DAYS.index(w["day"].lower()))
        return {"workouts": workouts, "count": len(workouts)}

    # delete: by id, or every workout on a day
    if "workout_id" not in args and day is None:
        raise ToolError("To delete I need the workout id or the day.")

    def delete(data: dict) -> list[dict]:
        workouts = data.get(ctx.user_id, [])
        gone = [w for w in workouts
                if w["id"] == args.get("workout_id") or ("workout_id" not in args and w["day"] == day)]
        data[ctx.user_id] = [w for w in workouts if w not in gone]
        return gone

    removed = await store.update(delete)
    if not removed:
        raise ToolError("I couldn't find that workout in the schedule.")
    return {"deleted": removed}


TOOL = Tool(
    name="workout_schedule",
    description="Add a workout to the member's weekly schedule, list their scheduled workouts, "
    "or delete one (by id or by day).",
    parameters=PARAMETERS,
    run=run,
)
