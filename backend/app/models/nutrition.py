from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import Field, PlainSerializer

from .common import Contract, Quantity


Nutrient = Annotated[Decimal, Field(ge=0), PlainSerializer(str, return_type=str, when_used="json")]


class NutritionBasis(str, Enum):
    per_100g = "per_100g"
    per_unit = "per_unit"
    per_serving = "per_serving"
    recipe_total = "recipe_total"


class NutritionFacts(Contract):
    calories_kcal: Nutrient
    protein_g: Nutrient
    carbohydrates_g: Nutrient
    fat_g: Nutrient
    reference_quantity: Quantity
    reference_unit: str
    basis: NutritionBasis
    source: str
    estimated: bool
