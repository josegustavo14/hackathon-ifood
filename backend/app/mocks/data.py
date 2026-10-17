import json
from functools import lru_cache
from pathlib import Path

from app.models.nutrition import NutritionFacts
from app.models.product import ProductCandidate
from app.models.recipe import MealPlan, Recipe

DATA_DIR = Path(__file__).with_name("data")


@lru_cache
def load_json(name: str) -> dict:
    with (DATA_DIR / name).open(encoding="utf-8") as file:
        return json.load(file)


@lru_cache
def recipe() -> Recipe:
    return Recipe.model_validate(load_json("recipe.json"))


@lru_cache
def products() -> tuple[ProductCandidate, ...]:
    return tuple(ProductCandidate.model_validate(item) for item in load_json("products.json")["products"])


@lru_cache
def nutrition_total() -> NutritionFacts:
    return NutritionFacts.model_validate(load_json("nutrition.json")["facts"])


def meal_plan(filename: str) -> MealPlan:
    return MealPlan.model_validate({**load_json("meal_plan.json"), "source_filename": filename})
