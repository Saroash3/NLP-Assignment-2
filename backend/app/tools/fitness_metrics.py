"""
Tool: calculate_fitness_metrics -- BMI, daily calorie needs, or an estimated one-rep max.

Formulas (standard, well-known ones so they are easy to defend):
  BMI            weight_kg / height_m^2, with the WHO categories
  Daily calories Mifflin-St Jeor BMR x activity factor (= TDEE, maintenance calories)
  One-rep max    Epley: weight x (1 + reps / 30)
"""
from __future__ import annotations

from app.tools.base import Tool, ToolContext, ToolError

ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}

PARAMETERS = {
    "type": "object",
    "properties": {
        "metric": {"type": "string", "enum": ["bmi", "daily_calories", "one_rep_max"]},
        "weight_kg": {"type": "number", "description": "body weight in kg (bmi, daily_calories)"},
        "height_cm": {"type": "number", "description": "height in cm (bmi, daily_calories)"},
        "height_ft": {"type": "number", "description": "height in feet, if given in feet (e.g. 6)"},
        "height_in": {"type": "number", "description": "extra inches with height_ft (e.g. 1 for 6'1\")"},
        "age": {"type": "integer", "description": "age in years (daily_calories)"},
        "sex": {"type": "string", "enum": ["male", "female"]},
        "activity_level": {"type": "string", "enum": list(ACTIVITY_FACTORS)},
        "lifted_kg": {"type": "number", "description": "weight lifted in kg (one_rep_max)"},
        "reps": {"type": "integer", "description": "reps done with lifted_kg (one_rep_max)"},
    },
    "required": ["metric"],
}


def _need(args: dict, *keys: str, what: str) -> None:
    missing = [k for k in keys if k not in args]
    if missing:
        raise ToolError(f"To calculate {what} I need: {', '.join(missing)}.")
    for k in keys:
        if args[k] <= 0:
            raise ToolError(f"'{k}' must be greater than zero.")


def bmi(weight_kg: float, height_cm: float) -> dict:
    value = weight_kg / (height_cm / 100) ** 2
    if value < 18.5:
        category = "underweight"
    elif value < 25:
        category = "normal weight"
    elif value < 30:
        category = "overweight"
    else:
        category = "obese"
    return {"bmi": round(value, 1), "category": category}


def daily_calories(weight_kg: float, height_cm: float, age: int, sex: str, activity_level: str) -> dict:
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "male" else -161)
    tdee = bmr * ACTIVITY_FACTORS[activity_level]
    return {
        "bmr_kcal": round(bmr),
        "maintenance_kcal": round(tdee),
        "weight_loss_kcal": round(tdee - 500),  # ~0.5 kg/week deficit
        "weight_gain_kcal": round(tdee + 300),  # lean-bulk surplus
        "activity_level": activity_level,
    }


def one_rep_max(lifted_kg: float, reps: int) -> dict:
    if reps > 12:
        raise ToolError("One-rep max estimates are only reliable for 12 reps or fewer.")
    estimate = lifted_kg if reps == 1 else lifted_kg * (1 + reps / 30)
    return {"one_rep_max_kg": round(estimate, 1), "formula": "Epley"}


def _height_and_weight_check(args: dict) -> None:
    """Feet/inches -> cm (exact, done here: the LLM turned "6 foot" into 720 cm in a live test),
    then reject impossible values instead of returning a nonsense BMI."""
    if "height_cm" not in args and "height_ft" in args:
        args["height_cm"] = round(args["height_ft"] * 30.48 + args.get("height_in", 0) * 2.54, 1)
    if "height_cm" in args and not 120 <= args["height_cm"] <= 230:
        raise ToolError(f"A height of {args['height_cm']:g} cm doesn't look right -- please give it "
                        "in centimetres or in feet and inches.")
    if "weight_kg" in args and not 30 <= args["weight_kg"] <= 300:
        raise ToolError(f"A weight of {args['weight_kg']:g} kg doesn't look right -- please check it.")


async def run(args: dict, ctx: ToolContext) -> dict:
    metric = args["metric"]
    _height_and_weight_check(args)
    if metric == "bmi":
        _need(args, "weight_kg", "height_cm", what="BMI")
        return bmi(args["weight_kg"], args["height_cm"])
    if metric == "daily_calories":
        _need(args, "weight_kg", "height_cm", "age", what="daily calories")
        if "sex" not in args:
            raise ToolError("To calculate daily calories I need: sex (male or female).")
        return daily_calories(args["weight_kg"], args["height_cm"], args["age"], args["sex"],
                              args.get("activity_level", "moderate"))
    _need(args, "lifted_kg", "reps", what="a one-rep max")
    return one_rep_max(args["lifted_kg"], args["reps"])


TOOL = Tool(
    name="calculate_fitness_metrics",
    description="Calculate BMI, daily calorie needs (maintenance, loss, gain) or an estimated "
    "one-rep max from the member's numbers.",
    parameters=PARAMETERS,
    run=run,
)
