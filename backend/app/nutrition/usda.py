"""USDA FoodData Central adapter and recipe nutrition calculation."""

import json
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

import httpx
from pydantic import Field, TypeAdapter

from app.models.common import Contract
from app.models.ingredient import Ingredient, Unit
from app.models.nutrition import (
    NutritionCalculation,
    NutritionFacts,
    NutritionSource,
    NutritionStatus,
    UnresolvedIngredient,
)
from app.models.recipe import Recipe

USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"
ROUND_TO = Decimal("0.01")
NUTRIENT_IDS = {"protein_g": 1003, "fat_g": 1004, "carbohydrates_g": 1005}
ENERGY_IDS = (2048, 2047, 1008)


class USDAIngredientMapping(Contract):
    aliases: list[str] = Field(min_length=1)
    fdc_id: int = Field(gt=0)
    expected_description: str
    unit_portion_modifier: str | None = None
    density_g_per_ml: Decimal | None = Field(default=None, gt=0)
    note: str | None = None


def normalize_name(value: str) -> str:
    without_accents = "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(without_accents.split())


@lru_cache
def ingredient_mappings() -> dict[str, USDAIngredientMapping]:
    path = Path(__file__).with_name("usda_mappings.json")
    with path.open(encoding="utf-8") as file:
        entries = TypeAdapter(list[USDAIngredientMapping]).validate_python(json.load(file))
    result: dict[str, USDAIngredientMapping] = {}
    for entry in entries:
        for alias in entry.aliases:
            key = normalize_name(alias)
            if not key or key in result:
                raise ValueError(f"Duplicate or empty USDA ingredient alias: {alias}")
            result[key] = entry
    return result


class USDAUpstreamError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class USDAClient:
    def __init__(self, api_key: str, client: httpx.AsyncClient):
        self.api_key = api_key
        self.client = client

    async def get_food(self, fdc_id: int) -> dict | None:
        try:
            response = await self.client.get(
                f"{USDA_BASE_URL}/food/{fdc_id}", params={"api_key": self.api_key}
            )
        except httpx.TimeoutException as error:
            raise USDAUpstreamError(504, "USDA request timed out") from error
        except httpx.RequestError as error:
            raise USDAUpstreamError(502, "USDA service is unavailable") from error
        if response.status_code == 404:
            return None
        if response.status_code == 429:
            raise USDAUpstreamError(503, "USDA rate limit reached")
        if response.status_code in (401, 403):
            raise USDAUpstreamError(503, "USDA API key was rejected")
        if response.status_code >= 400:
            raise USDAUpstreamError(502, "USDA service returned an error")
        try:
            payload = response.json()
        except ValueError as error:
            raise USDAUpstreamError(502, "USDA returned invalid JSON") from error
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("fdcId"), int)
            or not isinstance(payload.get("description"), str)
            or not isinstance(payload.get("foodNutrients"), list)
        ):
            raise USDAUpstreamError(502, "USDA returned an invalid food record")
        return payload


def decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result >= 0 else None


def nutrient_values(food: dict) -> dict[str, Decimal] | None:
    found: dict[int, Decimal] = {}
    nutrients = food.get("foodNutrients")
    if not isinstance(nutrients, list):
        return None
    for item in nutrients:
        if not isinstance(item, dict) or not isinstance(item.get("nutrient"), dict):
            continue
        nutrient = item["nutrient"]
        nutrient_id = nutrient.get("id")
        expected_unit = "kcal" if nutrient_id in ENERGY_IDS else "g"
        if nutrient_id not in (*ENERGY_IDS, *NUTRIENT_IDS.values()):
            continue
        if str(nutrient.get("unitName", "")).casefold() != expected_unit:
            continue
        amount = decimal_value(item.get("amount"))
        if amount is not None:
            found[nutrient_id] = amount
    energy = next((found[id_] for id_ in ENERGY_IDS if id_ in found), None)
    if energy is None or any(id_ not in found for id_ in NUTRIENT_IDS.values()):
        return None
    return {"calories_kcal": energy, **{name: found[id_] for name, id_ in NUTRIENT_IDS.items()}}


def ingredient_grams(ingredient: Ingredient, servings: int, original_servings: int, mapping: USDAIngredientMapping, food: dict) -> Decimal | None:
    quantity = ingredient.quantity * Decimal(servings) / original_servings
    if ingredient.unit == Unit.g:
        return quantity
    if ingredient.unit == Unit.kg:
        return quantity * 1000
    if ingredient.unit in (Unit.ml, Unit.l):
        if mapping.density_g_per_ml is None:
            return None
        milliliters = quantity * (1000 if ingredient.unit == Unit.l else 1)
        return milliliters * mapping.density_g_per_ml
    if ingredient.unit == Unit.unit and mapping.unit_portion_modifier:
        portions = food.get("foodPortions")
        if not isinstance(portions, list):
            return None
        for portion in portions:
            if not isinstance(portion, dict) or portion.get("modifier") != mapping.unit_portion_modifier:
                continue
            weight = decimal_value(portion.get("gramWeight"))
            amount = decimal_value(portion.get("amount"))
            if weight is not None and amount is not None and amount > 0:
                return quantity * weight / amount
    return None


class USDANutritionProvider:
    def __init__(self, client: USDAClient):
        self.client = client

    async def calculate(self, recipe: Recipe, servings: int, include_optional: bool = False) -> NutritionCalculation:
        sums = {name: Decimal("0") for name in ("calories_kcal", *NUTRIENT_IDS)}
        unresolved: list[UnresolvedIngredient] = []
        sources: list[NutritionSource] = []
        warnings: list[str] = []
        included = [ingredient for ingredient in recipe.ingredients if include_optional or not ingredient.optional]
        if not include_optional and len(included) != len(recipe.ingredients):
            warnings.append("Ingredientes opcionais foram excluídos; use include_optional=true para incluí-los.")
        mappings = ingredient_mappings()
        for ingredient in included:
            mapping = mappings.get(normalize_name(ingredient.name))
            if mapping is None:
                unresolved.append(UnresolvedIngredient(ingredient_id=ingredient.id, name=ingredient.name, reason="unmapped_ingredient"))
                continue
            food = await self.client.get_food(mapping.fdc_id)
            if food is None or food.get("fdcId") != mapping.fdc_id or food.get("description") != mapping.expected_description:
                unresolved.append(UnresolvedIngredient(ingredient_id=ingredient.id, name=ingredient.name, reason="source_record_unavailable"))
                continue
            grams = ingredient_grams(ingredient, servings, recipe.servings, mapping, food)
            if grams is None or grams <= 0:
                unresolved.append(UnresolvedIngredient(ingredient_id=ingredient.id, name=ingredient.name, reason="weight_conversion_unavailable"))
                continue
            values = nutrient_values(food)
            if values is None:
                unresolved.append(UnresolvedIngredient(ingredient_id=ingredient.id, name=ingredient.name, reason="nutrients_missing"))
                continue
            for name, value in values.items():
                sums[name] += value * grams / 100
            sources.append(NutritionSource(ingredient_id=ingredient.id, fdc_id=mapping.fdc_id, description=mapping.expected_description, grams=grams))
            if mapping.note:
                warnings.append(f"{ingredient.name}: {mapping.note}")
        if unresolved or not included:
            if not included:
                warnings.append("A receita não contém ingredientes incluídos no cálculo.")
            return NutritionCalculation(
                recipe_id=recipe.id, servings=servings, status=NutritionStatus.incomplete,
                total=None, per_serving=None, unresolved_ingredients=unresolved,
                sources=sources, warnings=warnings,
            )
        total = NutritionFacts(
            **{name: value.quantize(ROUND_TO, rounding=ROUND_HALF_UP) for name, value in sums.items()},
            reference_quantity="1", reference_unit="recipe", basis="recipe_total",
            source="USDA FoodData Central", estimated=True,
        )
        per_serving = NutritionFacts(
            **{name: (value / servings).quantize(ROUND_TO, rounding=ROUND_HALF_UP) for name, value in sums.items()},
            reference_quantity="1", reference_unit="serving", basis="per_serving",
            source="USDA FoodData Central", estimated=True,
        )
        return NutritionCalculation(
            recipe_id=recipe.id, servings=servings, status=NutritionStatus.complete,
            total=total, per_serving=per_serving, sources=sources, warnings=warnings,
        )
