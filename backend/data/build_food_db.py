"""
Build backend/data/foods_usda.json from the USDA FoodData Central downloads (public domain).

  Survey foods (FNDDS, 2024-10-31): ~5,400 foods "as eaten", incl. dishes (pizza, cake, curries)
  SR Legacy (2018-04):              ~7,800 basic foods (raw/cooked ingredients)

For each food we keep only what the nutrition tool needs: per-100 g calories, protein, carbs, fat,
fiber, sugar and sodium, plus up to 4 real portion weights ("1 slice" = 107 g). The two datasets
number nutrients differently (Survey uses nutrient numbers like 208 = energy, SR Legacy uses
nutrient ids like 1008 = energy), so both codes are mapped.

Usage (from backend/, one-time, needs internet):  python data/build_food_db.py
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "foods_usda.json"
SOURCES = {
    "survey": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_survey_food_csv_2024-10-31.zip",
    "sr": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip",
}
# our field -> (Survey nutrient number, SR Legacy nutrient id)
NUTRIENTS = {"calories": ("208", "1008"), "protein_g": ("203", "1003"), "carbs_g": ("205", "1005"),
             "fat_g": ("204", "1004"), "fiber_g": ("291", "1079"), "sugar_g": ("269", "2000"),
             "sodium_mg": ("307", "1093")}
MAX_PORTIONS = 4


def read_csv(archive: zipfile.ZipFile, name: str):
    path = next(p for p in archive.namelist() if p.endswith("/" + name))
    with archive.open(path) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))


def portion_label(row: dict) -> str:
    """Survey rows have "1 slice"; SR Legacy rows have amount + modifier ("1", "cup, chopped")."""
    description = row.get("portion_description") or ""
    if description == "Quantity not specified":
        return ""  # a default amount, not a real portion
    if description:
        return description
    modifier = (row.get("modifier") or "").strip()
    if not modifier or modifier.isdigit():  # numeric modifiers are internal codes (e.g. 90000)
        return ""
    return f"{float(row.get('amount') or 1):g} {modifier}"


def build(kind: str, url: str) -> list[dict]:
    print(f"downloading {kind} ...")
    archive = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url, timeout=120).read()))
    code_index = 0 if kind == "survey" else 1
    wanted = {codes[code_index]: field for field, codes in NUTRIENTS.items()}

    foods = {r["fdc_id"]: {"name": r["description"], "src": kind} for r in read_csv(archive, "food.csv")}
    for r in read_csv(archive, "food_nutrient.csv"):
        field = wanted.get(r["nutrient_id"])
        if field and r["fdc_id"] in foods and r["amount"]:
            foods[r["fdc_id"]][field] = round(float(r["amount"]), 1)
    for r in read_csv(archive, "food_portion.csv"):
        food = foods.get(r["fdc_id"])
        grams = float(r["gram_weight"] or 0)
        if food is None or grams <= 0 or len(food.setdefault("portions", [])) >= MAX_PORTIONS:
            continue
        label = portion_label(r)
        if label:
            food["portions"].append([label, round(grams, 1)])
    return [f for f in foods.values() if "calories" in f]  # skip foods without an energy value


def main() -> None:
    foods = [food for kind, url in SOURCES.items() for food in build(kind, url)]
    OUT.write_text(json.dumps({"_note": "USDA FoodData Central (public domain), values per 100 g. "
                               "Built by build_food_db.py.", "foods": foods},
                              separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(foods)} foods to {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
