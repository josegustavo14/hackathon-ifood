from pydantic import Field, HttpUrl, model_validator

from .common import Contract
from .ingredient import Ingredient


class Recipe(Contract):
    id: str
    name: str
    description: str | None = None
    servings: int = Field(gt=0)
    ingredients: list[Ingredient]
    instructions: list[str]
    preparation_time_minutes: int | None = Field(default=None, ge=0)
    source: str
    source_url: HttpUrl | None = None


class MealOption(Contract):
    name: str
    ingredients: list[Ingredient]


class MealAlternativeGroup(Contract):
    options: list[MealOption] = Field(min_length=2)
    choose: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def validate_choice_count(self):
        if self.choose > len(self.options):
            raise ValueError("choose cannot exceed the number of options")
        return self


class Meal(Contract):
    day: str
    name: str
    frequency_per_week: int = Field(ge=1, le=7)
    ingredients: list[Ingredient]
    alternative_groups: list[MealAlternativeGroup] = Field(default_factory=list)


class MealPlan(Contract):
    id: str
    source_filename: str
    days: list[str]
    meals: list[Meal]
    extraction_warnings: list[str] = Field(default_factory=list)
