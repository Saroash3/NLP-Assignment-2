"""
Tool: lookup_nutrition -- calories, protein, carbs and fat for a common food, from the local
JSON database backend/data/foods.json (42 foods, including Pakistani staples like roti and daal).

Matching: exact name or alias first, then the closest spelling (difflib), so "chiken breast"
or a slightly wrong ASR transcript ("bananas") still finds the food.
"""
from __future__ import annotations

import difflib
import json
from functools import lru_cache
from pathlib import Path

from app.tools.base import Tool, ToolContext, ToolError

FOODS_PATH = Path(__file__).resolve().parents[2] / "data" / "foods.json"

PARAMETERS = {
    "type": "object",
    "properties": {
        "food": {"type": "string", "description": "food name, e.g. 'egg' or 'chicken breast'"},
        "grams": {"type": "number", "description": "amount in grams (optional)"},
        "servings": {"type": "number", "description": "number of typical servings, e.g. 2 eggs (optional)"},
    },
    "required": ["food"],
}


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    """name/alias (lower case) -> food record. Loaded once."""
    foods = json.loads(FOODS_PATH.read_text(encoding="utf-8"))["foods"]
    index: dict[str, dict] = {}
    for food in foods:
        for key in [food["name"], *food["aliases"]]:
            index[key.lower()] = food
    return index


def find_food(query: str) -> dict | None:
    index = _index()
    key = query.lower().strip()
    if key in index:
        return index[key]
    close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=0.75)
    return index[close[0]] if close else None


async def run(args: dict, ctx: ToolContext) -> dict:
    food = find_food(args["food"])
    if food is None:
        raise ToolError(f"'{args['food']}' is not in my nutrition database.")
    serving = food.get("serving")
    if "grams" in args:
        grams, portion = args["grams"], f"{args['grams']:g} g"
    elif "servings" in args and serving:
        grams = args["servings"] * serving["grams"]
        portion = f"{args['servings']:g} x {serving['label']} ({grams:g} g in total)"
    elif serving:
        grams, portion = serving["grams"], f"{serving['label']} ({serving['grams']} g)"
    else:
        grams, portion = 100, "100 g"
    if grams <= 0:
        raise ToolError("The amount must be greater than zero.")
    factor = grams / 100
    totals = {k: round(v * factor, 1) for k, v in food["per_100g"].items()}
    totals["calories"] = round(totals["calories"])
    # "totals_for" (not "portion"): measured, the model doubled "2 x 1 egg, protein 13 g" to 26 g.
    return {"food": food["name"], "totals_for": portion, **totals}


TOOL = Tool(
    name="lookup_nutrition",
    description="Look up calories, protein, carbs and fat for a common food (optionally for a "
    "given number of grams or servings).",
    parameters=PARAMETERS,
    run=run,
)
