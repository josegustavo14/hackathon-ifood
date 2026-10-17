from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import Field, PlainSerializer, model_validator

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


class NutritionStatus(str, Enum):
    complete = "complete"
    incomplete = "incomplete"


class NutritionUnresolvedReason(str, Enum):
    unmapped_ingredient = "unmapped_ingredient"
    source_record_unavailable = "source_record_unavailable"
    weight_conversion_unavailable = "weight_conversion_unavailable"
    nutrients_missing = "nutrients_missing"


class UnresolvedIngredient(Contract):
    ingredient_id: str
    name: str
    reason: NutritionUnresolvedReason


class NutritionSource(Contract):
    ingredient_id: str
    fdc_id: int
    description: str
    grams: Quantity


class NutritionCalculation(Contract):
    recipe_id: str
    servings: int = Field(gt=0)
    status: NutritionStatus
    total: NutritionFacts | None
    per_serving: NutritionFacts | None
    unresolved_ingredients: list[UnresolvedIngredient] = Field(default_factory=list)
    sources: list[NutritionSource] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self):
        if self.status == NutritionStatus.complete and (self.total is None or self.per_serving is None or self.unresolved_ingredients):
            raise ValueError("Complete nutrition requires totals and no unresolved ingredients")
        if self.status == NutritionStatus.incomplete and (self.total is not None or self.per_serving is not None):
            raise ValueError("Incomplete nutrition must not present recipe totals")
        return self
