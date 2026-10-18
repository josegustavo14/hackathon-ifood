from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.models.ingredient import Ingredient, Unit
from app.models.recipe import Meal, MealAlternativeGroup, MealOption, MealPlan


class MealPlanParseError(ValueError):
    """Raised when extracted PDF text cannot produce a meal plan."""


DAY_NAMES = (
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
)

MEAL_NAMES = (
    "cafe da manha",
    "cafe da tarde",
    "lanche da manha",
    "lanche da tarde",
    "lanche",
    "almoco",
    "jantar",
    "ceia",
)

_NUMBER = r"(?:\d+\s*/\s*\d+|\d+(?:[.,]\d+)?)"
_UNIT = r"kg|g|ml|l|unidades?|ovos?|x[ií]caras?|colheres?(?: de (?:sopa|cha))?"
_QUANTITY_FIRST = re.compile(rf"^(?P<quantity>{_NUMBER})\s*(?P<unit>{_UNIT})?\s+(?P<name>.+)$", re.I)
_QUANTITY_LAST = re.compile(rf"^(?P<name>.+?)\s*[:\-]?\s*(?P<quantity>{_NUMBER})\s*(?P<unit>{_UNIT})$", re.I)
_DAY = re.compile(r"^(?:dia\s*[:\-]?\s*)?(segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)\b(?:\s*[-:|]\s*(.*))?$", re.I)
_MEAL = re.compile(r"^(café da manhã|cafe da manha|café da tarde|cafe da tarde|lanche da manhã|lanche da manha|lanche da tarde|lanche|almoço|almoco|jantar|ceia)\s*[:\-|]?\s*(.*)$", re.I)


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char)).casefold()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _plain(value)).strip("-")
    return normalized or "ingredient"


def _decimal(value: str) -> Decimal:
    try:
        value = value.replace(",", ".").replace(" ", "")
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            result = Decimal(numerator) / Decimal(denominator)
        else:
            result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid quantity: {value}") from exc
    if result <= 0:
        raise ValueError("quantity must be positive")
    return result


def _unit_and_notes(raw_unit: str | None) -> tuple[Unit, str | None]:
    if not raw_unit:
        return Unit.unit, None
    normalized = _plain(raw_unit)
    if normalized == "kg":
        return Unit.kg, None
    if normalized == "g":
        return Unit.g, None
    if normalized == "ml":
        return Unit.ml, None
    if normalized == "l":
        return Unit.l, None
    if normalized in {"xicaras", "colher", "colheres", "colheres de sopa", "colheres de cha"}:
        return Unit.unit, f"medida caseira original: {raw_unit}"
    return Unit.unit, None


def _parse_ingredient(value: str) -> Ingredient | None:
    value = re.sub(r"^(?:[\-•*]\s*|\d+[.)]\s*)", "", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    match = _QUANTITY_FIRST.match(value) or _QUANTITY_LAST.match(value)
    if not match:
        return None

    name = match.group("name").strip(" -:.")
    if not name:
        return None
    quantity = _decimal(match.group("quantity"))
    unit, notes = _unit_and_notes(match.groupdict().get("unit"))
    name = re.sub(r"^(de|do|da|dos|das)\s+", "", name, flags=re.I)
    return Ingredient(id=_slug(name), name=name, quantity=quantity, unit=unit, notes=notes)


def _split_ingredients(value: str) -> list[str]:
    value = re.sub(r"\s+(?:e|mais)\s+(?=\d)", ";", value, flags=re.I)
    return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]


def _ingredients(value: str, warnings: list[str], context: str) -> list[Ingredient]:
    result: list[Ingredient] = []
    for part in _split_ingredients(value):
        if _plain(part) in {"a gosto", "quanto baste", "qb"} or _plain(part).endswith(" a gosto"):
            warnings.append(f"Quantidade não especificada para {context}: {part}")
            continue
        ingredient = _parse_ingredient(part)
        if ingredient is None:
            warnings.append(f"Não foi possível interpretar o ingrediente em {context}: {part}")
            continue
        result.append(ingredient)
    return result


def _day_name(value: str) -> str:
    return value.strip().capitalize()


def parse(text: str, source_filename: str) -> MealPlan:
    """Convert a simple text/table extraction into the shared MealPlan contract.

    Supported input is intentionally conservative: day and meal headings followed by
    ingredients such as ``100 g arroz; 1 unidade de ovo``. Ambiguous values become
    warnings instead of fabricated quantities.
    """
    warnings: list[str] = []
    days: list[str] = []
    meals: list[Meal] = []
    current_day: str | None = None
    current_meal: Meal | None = None

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" \t|•")
        if not line:
            continue

        day_match = _DAY.match(line)
        if day_match:
            current_day = _day_name(day_match.group(1))
            if current_day not in days:
                days.append(current_day)
            current_meal = None
            inline = day_match.group(2)
            if inline:
                meal_match = _MEAL.match(inline.strip())
                if meal_match:
                    current_meal = Meal(
                        day=current_day,
                        name=meal_match.group(1).strip(),
                        frequency_per_week=7,
                        ingredients=_ingredients(meal_match.group(2), warnings, inline) if meal_match.group(2) else [],
                    )
                    meals.append(current_meal)
            continue

        meal_match = _MEAL.match(line)
        if meal_match and current_day:
            current_meal = Meal(
                day=current_day,
                name=meal_match.group(1).strip(),
                frequency_per_week=7,
                ingredients=_ingredients(meal_match.group(2), warnings, line) if meal_match.group(2) else [],
            )
            meals.append(current_meal)
            continue

        # A compact table format: Dia | Refeição | Ingredientes.
        columns = [column.strip() for column in line.split("|")]
        if len(columns) >= 3 and _plain(columns[0]) in DAY_NAMES:
            current_day = _day_name(columns[0])
            if current_day not in days:
                days.append(current_day)
            current_meal = Meal(
                day=current_day,
                name=columns[1],
                frequency_per_week=7,
                ingredients=_ingredients(columns[2], warnings, columns[1]),
            )
            meals.append(current_meal)
            continue

        if current_meal is None:
            warnings.append(f"Linha sem dia ou refeição identificada: {line}")
            continue

        # Keep alternatives separate. The line format is: "Alternativas: 1 banana ou 1 maçã".
        if _plain(line).startswith("alternativa") or " ou " in _plain(line):
            value = re.sub(r"^[^:]+:\s*", "", line)
            options = [option.strip() for option in re.split(r"\s+ou\s+", value, flags=re.I)]
            parsed_options = []
            for option in options:
                parsed = _ingredients(option, warnings, current_meal.name)
                if parsed:
                    parsed_options.append(MealOption(name=option, ingredients=parsed))
            if len(parsed_options) >= 2:
                current_meal.alternative_groups.append(MealAlternativeGroup(options=parsed_options, choose=1))
            continue

        current_meal.ingredients.extend(_ingredients(line, warnings, current_meal.name))

    if not meals:
        raise MealPlanParseError("No meals could be identified in the PDF")
    if not days:
        days = sorted({meal.day for meal in meals})

    return MealPlan(
        id=f"meal-plan-{_slug(source_filename)}",
        source_filename=source_filename,
        days=days,
        meals=meals,
        extraction_warnings=warnings,
    )
