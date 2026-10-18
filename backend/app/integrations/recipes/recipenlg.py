"""Optional, local RecipeNLG CSV index. The dataset is never downloaded by the app.

RecipeNLG is licensed separately for non-commercial research and education.
Only recipes with explicit servings and fully understood ingredient quantities are
exposed to the shopping API; incomplete rows remain in the index but are skipped.
"""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
from decimal import Decimal
from pathlib import Path

from app.integrations.recipes import RecipeProviderError, _slug
from app.models.ingredient import Ingredient, Unit
from app.models.recipe import Recipe


def _list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError, TypeError):
            return []
    return [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def _ingredient(raw: str, index: int) -> Ingredient | None:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?|\d+\s*/\s*\d+)\s*"
        r"(kg|kilograms?|g|grams?|ml|milliliters?|l|liters?)\s+(?:of\s+)?(.+?)\s*",
        raw, re.I,
    )
    if not match:
        count = re.fullmatch(r"\s*(\d+)\s+(.+?)\s*", raw)
        if not count or re.match(r"(?:cups?|tbsp|tsp|tablespoons?|teaspoons?|ounces?|pounds?)\b", count[2], re.I):
            return None
        return Ingredient(id=f"{_slug(count[2])}-{index}", name=count[2], quantity=Decimal(count[1]), unit=Unit.unit)
    number = match[1].replace(" ", "")
    quantity = (Decimal(number.split("/")[0]) / Decimal(number.split("/")[1])) if "/" in number else Decimal(number)
    if quantity <= 0:
        return None
    unit = {
        "kilogram": Unit.kg, "kilograms": Unit.kg, "kg": Unit.kg,
        "g": Unit.g, "gram": Unit.g, "grams": Unit.g,
        "ml": Unit.ml, "milliliter": Unit.ml, "milliliters": Unit.ml,
        "l": Unit.l, "liter": Unit.l, "liters": Unit.l,
    }[match[2].lower()]
    name = match[3].strip()
    return Ingredient(id=f"{_slug(name)}-{index}", name=name, quantity=quantity, unit=unit)


def _recipe(row: sqlite3.Row) -> Recipe | None:
    raw_ingredients = _list(row["ingredients"])
    ingredients = [_ingredient(raw, index) for index, raw in enumerate(raw_ingredients, 1)]
    directions = _list(row["directions"])
    try:
        servings = int(row["servings"])
    except (TypeError, ValueError):
        servings = None
    if servings is not None and servings <= 0 or not raw_ingredients or any(item is None for item in ingredients) or not directions:
        return None
    link = row["link"] or None
    if link and not link.startswith(("http://", "https://")):
        link = None
    try:
        return Recipe(
            id=f"recipenlg-{row['id']}", name=row["title"], servings=servings or 1,
            ingredients=ingredients, instructions=directions, source="recipenlg" if servings else "recipenlg_batch",
            source_url=link,
            description=("Receita do conjunto RecipeNLG; confira os dados antes de comprar." if servings else
                         "Rendimento não informado no RecipeNLG. As quantidades representam uma receita completa (1 lote), não uma porção."),
        )
    except ValueError:
        return None


def build_index(csv_path: Path, index_path: Path) -> int:
    """Stream a user-supplied full_dataset.csv into a local SQLite FTS index."""
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=index_path.parent, suffix=".sqlite3", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    connection = sqlite3.connect(temporary_path)
    try:
        connection.execute("CREATE TABLE recipes (id INTEGER PRIMARY KEY, title TEXT NOT NULL, ingredients TEXT NOT NULL, directions TEXT NOT NULL, link TEXT, source TEXT, servings TEXT)")
        connection.execute("CREATE VIRTUAL TABLE recipe_titles USING fts5(title, content='recipes', content_rowid='id')")
        count = 0
        with csv_path.open(newline="", encoding="utf-8-sig") as source:
            csv.field_size_limit(10 * 1024 * 1024)
            reader = csv.DictReader(source)
            required = {"title", "ingredients", "directions"}
            if not required.issubset(reader.fieldnames or []):
                raise RecipeProviderError("RecipeNLG CSV must contain title, ingredients and directions")
            for row in reader:
                if row.get("source") not in (None, "Gathered"):
                    continue
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                cursor = connection.execute(
                    "INSERT INTO recipes(title, ingredients, directions, link, source, servings) VALUES (?, ?, ?, ?, ?, ?)",
                    (title, row.get("ingredients") or "", row.get("directions") or "", row.get("link"), row.get("source"), row.get("servings")),
                )
                connection.execute("INSERT INTO recipe_titles(rowid, title) VALUES (?, ?)", (cursor.lastrowid, title))
                count += 1
                if count % 10000 == 0:
                    connection.commit()
        connection.commit()
        connection.close()
        os.replace(temporary_path, index_path)
        return count
    finally:
        connection.close()
        temporary_path.unlink(missing_ok=True)


class RecipeNLGProvider:
    def __init__(self, index_path: Path):
        self.index_path = index_path

    async def search(self, query: str) -> list[Recipe]:
        if not self.index_path.is_file():
            return []
        plain = unicodedata.normalize("NFKD", query.casefold())
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        aliases = {"lasanha": "lasagna", "macarrao": "pasta", "frango": "chicken", "carne": "beef",
                   "arroz": "rice", "bolo": "cake", "sopa": "soup", "batata": "potato"}
        terms = [aliases.get(term, term) for term in re.findall(r"[a-z0-9]+", plain) if term not in {"de", "da", "do", "com", "a", "o"}][:8]
        if not terms:
            return []
        with sqlite3.connect(self.index_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT r.* FROM recipe_titles t JOIN recipes r ON r.id=t.rowid WHERE recipe_titles MATCH ? ORDER BY rank LIMIT 200",
                (" ".join(f'"{term}"' for term in terms),),
            ).fetchall()
        recipes = [_recipe(row) for row in rows]
        return [recipe for recipe in recipes if recipe is not None][:10]

    async def get_by_id(self, recipe_id: str) -> Recipe | None:
        if not self.index_path.is_file() or not re.fullmatch(r"recipenlg-\d+", recipe_id):
            return None
        with sqlite3.connect(self.index_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM recipes WHERE id=?", (int(recipe_id.split("-")[1]),)).fetchone()
        return _recipe(row) if row else None
