from enum import Enum

from pydantic import Field, model_validator

from .common import Contract, Money
from .ingredient import Ingredient
from .product import ProductCandidate


class ShoppingItemStatus(str, Enum):
    pending = "pending"
    matched = "matched"
    unavailable = "unavailable"
    needs_review = "needs_review"


class ShoppingItem(Contract):
    ingredient: Ingredient
    selected_product: ProductCandidate | None = None
    purchase_quantity: int = Field(ge=0)
    total_price: Money
    status: ShoppingItemStatus


class ShoppingListStatus(str, Enum):
    pending = "pending"
    ready_for_review = "ready_for_review"
    needs_review = "needs_review"


class ShoppingList(Contract):
    id: str
    recipe_id: str | None = None
    items: list[ShoppingItem]
    estimated_subtotal: Money
    currency: str = "BRL"
    unresolved_ingredients: list[Ingredient]
    status: ShoppingListStatus

    @model_validator(mode="after")
    def validate_currency(self):
        if self.currency != "BRL":
            raise ValueError("currency must be BRL")
        return self
