"""Inputs and detailed outputs for the independent shopping engine."""

from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import Field, PlainSerializer, field_validator, model_validator

from app.models.common import Contract, Money
from app.models.product import ProductCandidate
from app.models.shopping import ShoppingItemStatus, ShoppingListStatus

Amount = Annotated[Decimal, PlainSerializer(str, return_type=str, when_used="json")]


class ShoppingUnit(str, Enum):
    g = "g"
    kg = "kg"
    ml = "ml"
    l = "l"
    unit = "unit"
    cup = "cup"
    tablespoon = "tablespoon"
    teaspoon = "teaspoon"


UNIT_ALIASES = {
    "g": "g", "grama": "g", "gramas": "g", "kg": "kg",
    "ml": "ml", "l": "l", "litro": "l", "litros": "l",
    "unit": "unit", "unidade": "unit", "unidades": "unit",
    "cup": "cup", "xicara": "cup", "xícara": "cup", "xícaras": "cup",
    "tablespoon": "tablespoon", "colher de sopa": "tablespoon", "colheres de sopa": "tablespoon",
    "teaspoon": "teaspoon", "colher de chá": "teaspoon", "colheres de chá": "teaspoon",
}


def parse_unit(value: object) -> ShoppingUnit:
    if isinstance(value, ShoppingUnit):
        return value
    if not isinstance(value, str):
        raise ValueError("unit must be a string")
    normalized = value.strip().casefold()
    if normalized not in UNIT_ALIASES:
        raise ValueError(f"unsupported unit: {value}")
    return ShoppingUnit(UNIT_ALIASES[normalized])


class ShoppingIngredient(Contract):
    id: str
    name: str = Field(min_length=1)
    quantity: Amount | None = Field(default=None, gt=0)
    unit: ShoppingUnit
    category: str | None = None
    optional: bool = False
    required_tags: list[str] = Field(default_factory=list)
    authorized_product_ids: list[str] = Field(default_factory=list)

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: object) -> ShoppingUnit:
        return parse_unit(value)


class ShoppingRecipe(Contract):
    id: str
    servings: int = Field(gt=0)
    target_servings: int = Field(gt=0)
    ingredients: list[ShoppingIngredient]


class StockIngredient(Contract):
    name: str = Field(min_length=1)
    quantity: Amount = Field(gt=0)
    unit: ShoppingUnit
    category: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: object) -> ShoppingUnit:
        return parse_unit(value)


class CulinaryConversion(Contract):
    ingredient_name: str = Field(min_length=1)
    from_unit: ShoppingUnit
    to_unit: ShoppingUnit
    amount_per_unit: Amount = Field(gt=0)
    source: str = Field(min_length=1)

    @field_validator("from_unit", "to_unit", mode="before")
    @classmethod
    def normalize_unit(cls, value: object) -> ShoppingUnit:
        return parse_unit(value)

    @model_validator(mode="after")
    def check_conversion(self):
        if self.from_unit not in {ShoppingUnit.cup, ShoppingUnit.tablespoon, ShoppingUnit.teaspoon}:
            raise ValueError("from_unit must be a culinary measure")
        if self.to_unit not in {ShoppingUnit.g, ShoppingUnit.ml}:
            raise ValueError("to_unit must be g or ml")
        return self


class ShoppingPlanRequest(Contract):
    recipes: list[ShoppingRecipe] = Field(min_length=1)
    stock: list[StockIngredient] = Field(default_factory=list)
    products: list[ProductCandidate] = Field(default_factory=list)
    conversions: list[CulinaryConversion] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)
    merchant_id: str | None = None
    delivery_fees: dict[str, Money] = Field(default_factory=dict)
    include_optional: bool = False

    @model_validator(mode="after")
    def unique_products(self):
        ids = [product.id for product in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError("product ids must be unique")
        return self


class ProductSelection(Contract):
    product: ProductCandidate
    packages: int = Field(gt=0)
    bought_quantity: Amount = Field(gt=0)
    total_price: Money


class ShoppingPlanItem(Contract):
    ingredient_ids: list[str]
    name: str
    category: str | None = None
    unit: ShoppingUnit | None = None
    required_quantity: Amount | None = None
    stock_quantity: Amount | None = None
    stock_used_quantity: Amount | None = None
    net_quantity: Amount | None = None
    selections: list[ProductSelection] = Field(default_factory=list)
    bought_quantity: Amount | None = None
    excess_quantity: Amount | None = None
    total_price: Money = Decimal("0.00")
    status: ShoppingItemStatus
    reason: str
    optimal: bool = True


class ShoppingPlan(Contract):
    items: list[ShoppingPlanItem]
    estimated_subtotal: Money
    delivery_fee: Money | None = None
    estimated_total: Money | None = None
    currency: str = "BRL"
    merchant_id: str | None = None
    unresolved_ingredients: list[str]
    status: ShoppingListStatus
    optimal: bool
    warnings: list[str] = Field(default_factory=list)
