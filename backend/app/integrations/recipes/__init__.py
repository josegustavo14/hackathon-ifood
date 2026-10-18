from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.ingredient import Ingredient, Unit
from app.models.recipe import Recipe


class RecipeProviderError(RuntimeError):
    """Raised when the external recipe provider cannot be read or normalized."""


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char)).casefold()
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "recipe"


def _first(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def _int_value(value: Any, default: int) -> int:
    match = re.search(r"\d+", str(value)) if value is not None else None
    return int(match.group()) if match else default


def _quantity(value: Any) -> tuple[Decimal, Unit, str | None]:
    raw = str(value).strip()
    match = re.match(r"^(?P<number>\d+(?:[.,]\d+)?|\d+\s*/\s*\d+)\s*(?P<unit>kg|g|ml|l|un(?:id(?:ade)?s?)?|x[ií]cara(?:s)?|colher(?:es)?(?:\s+de\s+(?:sopa|chá))?|ovo(?:s)?)?\b", raw, re.I)
    if not match:
        raise ValueError("quantity not found")
    number = match.group("number").replace(",", ".").replace(" ", "")
    quantity = Decimal(number.split("/")[0]) / Decimal(number.split("/")[1]) if "/" in number else Decimal(number)
    unit_text = (match.group("unit") or "unit").casefold()
    if unit_text == "kg":
        unit = Unit.kg
    elif unit_text == "g":
        unit = Unit.g
    elif unit_text == "ml":
        unit = Unit.ml
    elif unit_text == "l":
        unit = Unit.l
    else:
        unit = Unit.unit
    note = None if unit_text in {"kg", "g", "ml", "l", "unit"} else f"medida original: {match.group('unit')}"
    return quantity, unit, note


def _ingredient(value: Any, index: int) -> Ingredient | None:
    if isinstance(value, dict):
        name = _first(value, "name", "nome", "ingredient", "ingrediente", "nomesIngrediente")
        quantity_value = _first(value, "quantity", "quantidade", "amount", "medida")
        unit_value = _first(value, "unit", "unidade")
        if isinstance(name, list):
            name = ", ".join(str(item) for item in name)
        if name is None or quantity_value is None:
            return None
        raw = f"{quantity_value} {unit_value or ''}".strip()
    else:
        raw = str(value).strip()
        name = None
    try:
        quantity, unit, notes = _quantity(raw)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None
    if name is None:
        name = raw[re.match(r"^.*?\s", raw).end():].strip() if re.match(r"^.*?\s", raw) else raw
    name = re.sub(r"^(?:de|do|da|dos|das)\s+", "", str(name).strip(), flags=re.I)
    if not name:
        return None
    return Ingredient(id=_slug(name) or f"ingredient-{index}", name=name, quantity=quantity, unit=unit, notes=notes)


def normalize_recipe(payload: dict[str, Any], *, source_url: str | None = None, source: str = "recipes_api") -> Recipe:
    name = _first(payload, "name", "nome", "receita", "title")
    if not name:
        raise RecipeProviderError("Recipe response has no name")
    raw_ingredients = _first(payload, "ingredients", "ingredientes", "IngredientsBase", "ingredientesBase") or []
    if isinstance(raw_ingredients, str):
        raw_ingredients = re.split(r"[,;]\s*", raw_ingredients)
    ingredients = [item for index, value in enumerate(raw_ingredients, 1) if (item := _ingredient(value, index))]
    instructions = _first(payload, "instructions", "instrucoes", "modo_preparo", "preparo") or []
    if isinstance(instructions, str):
        instructions = [part.strip() for part in re.split(r"(?:\d+[.)]\s*|\n+)", instructions) if part.strip()]
    recipe_id = str(_first(payload, "id", "recipe_id") or _slug(str(name)))
    servings_value = _first(payload, "servings", "porcoes", "rendimento") or 1
    servings = max(1, _int_value(servings_value, 1))
    preparation_time = _first(payload, "preparation_time_minutes", "tempo_preparo", "tempo")
    raw_url = _first(payload, "source_url", "url", "link", "link_imagem") or source_url
    return Recipe(
        id=recipe_id,
        name=str(name),
        description=_first(payload, "description", "descricao"),
        servings=servings,
        ingredients=ingredients,
        instructions=[str(item) for item in instructions],
        preparation_time_minutes=_int_value(preparation_time, 0) if preparation_time is not None else None,
        source=source,
        source_url=raw_url,
    )


