"""
Tool: lookup_nutrition -- calories, protein, carbs, fat (+ fiber, sugar, sodium) for almost any food.

Two local tables, searched in this order:
  1. backend/data/foods.json       42 hand-made entries incl. Pakistani staples and aliases
                                   ("anda" -> egg, "chawal" -> rice, "daal", "roti")
  2. backend/data/foods_usda.json  13,224 foods from USDA FoodData Central (public domain): Survey
                                   foods "as eaten" (pizza, cake, curries...) + SR Legacy ingredients,
                                   with real portion weights ("1 piece, medium pizza" = 86 g).
                                   Built once by backend/data/build_food_db.py.

USDA matching: every word of the query must appear in the food's name (plurals folded: "eggs" ->
"egg"); among those, prefer names whose FIRST part (before the comma, e.g. "Pizza, cheese") holds
the query words, then the shortest name, then Survey ("as eaten") over raw ingredients.

Amount: grams if given; else a portion ("slice", "cup", "piece") from the food's USDA portions,
times `servings`; else one typical serving; else 100 g.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

from app.tools.base import Tool, ToolContext, ToolError

DATA = Path(__file__).resolve().parents[2] / "data"
FOODS_PATH = DATA / "foods.json"
USDA_PATH = DATA / "foods_usda.json"

PARAMETERS = {
    "type": "object",
    "properties": {
        "food": {"type": "string", "description": "food or dish, e.g. 'egg', 'chicken breast', 'cheese pizza'"},
        "grams": {"type": "number", "description": "amount in grams (optional)"},
        "servings": {"type": "number", "description": "how many items/portions, e.g. 2 eggs (optional)"},
        "portion": {"type": "string", "description": "portion word, e.g. 'slice', 'cup', 'piece', 'bowl' (optional)"},
    },
    "required": ["food"],
}

NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg")
PORTION_WORDS = {"slice", "piece", "cup", "bowl", "plate", "glass", "tablespoon", "tbsp", "teaspoon",
                 "tsp", "serving", "scoop", "bar", "can", "bottle"}
STOP_WORDS = {"a", "an", "the", "of", "in", "with", "and", "some", "my", "one", "two", "three", "how",
              "much", "many", "calorie", "nutrition", "nutrient", "breakdown", "gram", "g", "kg",
              "medium", "large", "small", "big", "regular", "plain"} | PORTION_WORDS


# Everyday words -> the words USDA uses ("donut" is "Doughnut", a burger is a "Hamburger").
SYNONYMS = {"donut": "doughnut", "milkshake": "milk shake", "burger": "hamburger", "coke": "soft drink cola",
            "coca": "", "cola": "soft drink cola", "soda": "soft drink", "fries": "french fries",
            "chip": "potato chip", "softdrink": "soft drink"}
# Versions nobody means unless they say so ("cola" should not find "Soft drink, cola, diet").
SPECIAL_VERSIONS = {"diet", "free", "low", "reduced", "light", "lite", "unsweetened", "decaffeinated",
                    "dietetic", "baby", "infant", "dry", "dehydrated", "powder", "frozen"}
# Everyday portion words, preferred for the default portion ("1 cup" over "1 fl oz").
EVERYDAY_PORTIONS = {"slice", "piece", "cup", "medium", "serving", "can", "bowl", "glass", "bottle",
                     "egg", "doughnut", "hamburger", "sandwich", "bar", "fruit", "wedge"}
# A pizza "slice" is a "piece" in USDA's portion names (and vice versa).
PORTION_ALIASES = {"slice": {"slice", "piece"}, "piece": {"piece", "slice"}}


def _words(text: str) -> list[str]:
    """Lower-case words, plurals folded ("eggs" -> "egg", "berries" -> "berry")."""
    out = []
    for w in re.findall(r"[a-z]+", text.lower()):
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("es") and w[:-2].endswith(("ch", "sh", "ss", "x", "o")):
            w = w[:-2]
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        out.append(w)
    return out


@lru_cache(maxsize=1)
def _curated() -> dict[str, dict]:
    """name/alias (lower case) -> curated food record. Loaded once."""
    index: dict[str, dict] = {}
    for food in json.loads(FOODS_PATH.read_text(encoding="utf-8"))["foods"]:
        for key in [food["name"], *food["aliases"]]:
            index[key.lower()] = food
    return index


@lru_cache(maxsize=1)
def _usda() -> list[tuple[dict, frozenset, frozenset, int]]:
    """(food, all name words, words of the name's first part, number of words). Loaded once."""
    if not USDA_PATH.exists():  # table not built: the curated foods still work
        return []
    rows = []
    for food in json.loads(USDA_PATH.read_text(encoding="utf-8"))["foods"]:
        words = _words(food["name"])
        first = _words(food["name"].split(",")[0])
        rows.append((food, frozenset(words), frozenset(first), len(words)))
    return rows


def find_curated(query: str) -> dict | None:
    index = _curated()
    key = query.lower().strip()
    if key in index:
        return index[key]
    close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=0.85)
    return index[close[0]] if close else None


def _has_portion(portions: list[list], requested: str | None) -> bool:
    if not requested:
        return False
    names = PORTION_ALIASES.get(requested, {requested})
    return any(names & set(_words(label)) for label, _ in portions)


def search_usda(query: str, requested: str | None = None) -> dict | None:
    query = " ".join(SYNONYMS.get(w, w) for w in _words(query))
    wanted = list(dict.fromkeys(w for w in _words(query) if w not in STOP_WORDS))
    if not wanted:
        return None
    found = _best_match(wanted, requested)
    if found is None and len(wanted) > 1:
        # No food has ALL the words ("beef burger"): retry without one word, keeping the last
        # (usually the dish itself: "burger").
        for drop in range(len(wanted) - 1):
            found = _best_match(wanted[:drop] + wanted[drop + 1:], requested)
            if found:
                break
    return found


def _best_match(wanted: list[str], requested: str | None) -> dict | None:
    best, best_score = None, None
    for food, words, first, size in _usda():
        if not all(w in words for w in wanted):
            continue
        name_start = _words(food["name"])[0]
        score = (first == frozenset(wanted),          # "Pizza, ..." for "pizza" (not "Dessert pizza")
                 _has_portion(food.get("portions", []), requested),  # has the asked-for portion
                 not (SPECIAL_VERSIONS & words) - set(wanted),       # not "diet"/"powder" unless asked
                 name_start in wanted,                 # the name starts with an asked-for word
                 "nfs" in words,                       # USDA's generic "not further specified" entry
                 sum(w in first for w in wanted),      # asked-for words in the name's first part
                 -size, food["src"] == "survey")       # then the simplest name, "as eaten" first
        if best_score is None or score > best_score:
            best, best_score = food, score
    return best


def _amount(args: dict, portions: list[list], requested: str | None) -> tuple[float, str]:
    """-> (grams, human label of the amount)."""
    servings = args.get("servings", 1)
    if "grams" in args:
        return args["grams"], f"{args['grams']:g} g"
    if requested:
        names = PORTION_ALIASES.get(requested, {requested})
        for label, grams in portions:
            if names & set(_words(label)):
                return servings * grams, f"{servings:g} x {label} ({servings * grams:g} g in total)"
    if portions:
        # Default: an everyday portion of a realistic size (not "1 fry" = 5 g, not "1 fl oz",
        # not "1 miniature melon" = 1.3 kg); else any realistic size; else the first.
        realistic = [p for p in portions if 30 <= p[1] <= 700]
        label, grams = next((p for p in realistic if EVERYDAY_PORTIONS & set(_words(p[0]))),
                            realistic[0] if realistic else portions[0])
        return servings * grams, f"{servings:g} x {label} ({servings * grams:g} g in total)"
    return 100.0 * servings, f"{100 * servings:g} g"


def lookup(args: dict) -> dict:
    query = args["food"]
    requested = args.get("portion") or next((w for w in _words(query) if w in PORTION_WORDS), None)
    requested = (_words(requested) or [None])[0] if requested else None
    core = " ".join(w for w in _words(query) if w not in STOP_WORDS)

    curated = find_curated(query) or (find_curated(core) if core else None)
    if curated:
        serving = curated.get("serving")
        portions = [[serving["label"], serving["grams"]]] if serving else []
        per_100g, name, source = curated["per_100g"], curated["name"], "Zor food table"
    else:
        usda = search_usda(query, requested)
        if usda is None:
            raise ToolError(f"'{query}' is not in my nutrition database (13,000+ foods). Try a "
                            "simpler or more common name, e.g. 'cheese pizza' or 'boiled egg'.")
        portions = usda.get("portions", [])
        per_100g, name, source = usda, usda["name"], "USDA FoodData Central"

    grams, label = _amount(args, portions, requested)
    if grams <= 0:
        raise ToolError("The amount must be greater than zero.")
    factor = grams / 100
    totals = {k: round(per_100g[k] * factor, 1) for k in NUTRIENTS if per_100g.get(k) is not None}
    totals["calories"] = round(totals["calories"])
    # "totals_for" (not "portion"): measured, the model doubled "2 x 1 egg, protein 13 g" to 26 g.
    return {"food": name, "totals_for": label, **totals, "source": source}


async def run(args: dict, ctx: ToolContext) -> dict:
    # Searching 13,000 names is CPU work: keep it off the event loop.
    return await asyncio.to_thread(lookup, args)


TOOL = Tool(
    name="lookup_nutrition",
    description="Look up calories, protein, carbs, fat, fiber and sugar for almost any food or dish "
    "(13,000+ foods), for a given amount in grams, servings or a portion like a slice or a cup.",
    parameters=PARAMETERS,
    run=run,
)
