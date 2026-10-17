from enum import Enum

from .common import Contract, Quantity


class Unit(str, Enum):
    g = "g"
    kg = "kg"
    ml = "ml"
    l = "l"
    unit = "unit"


class Ingredient(Contract):
    id: str
    name: str
    quantity: Quantity
    unit: Unit
    optional: bool = False
    notes: str | None = None
