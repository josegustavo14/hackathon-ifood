import asyncio
import csv
from pathlib import Path

from app.integrations.recipes.provider import CombinedRecipeProvider, RecipeRegistry
from app.integrations.recipes.recipenlg import build_index
from app.models.recipe import Recipe


def test_local_recipenlg_index_and_safe_normalization(tmp_path: Path):
    csv_path = tmp_path / "full_dataset.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["title", "ingredients", "directions", "link", "source", "servings"])
        writer.writeheader()
        writer.writerow({"title": "Beef Stew", "ingredients": "['500 g beef', '2 onions']", "directions": "['Cook the beef.', 'Add onions.']", "link": "https://example.com/stew", "source": "Gathered", "servings": "4"})
        writer.writerow({"title": "Cup Cake", "ingredients": "['1 cup flour']", "directions": "['Bake.']", "source": "Gathered", "servings": "4"})
        writer.writerow({"title": "Rice Bowl", "ingredients": "['250 g rice']", "directions": "['Cook rice.']", "source": "Gathered"})
        writer.writerow({"title": "Old Beef", "ingredients": "['500 g beef']", "directions": "['Cook.']", "source": "Recipes1M", "servings": "4"})
    index = tmp_path / "recipes.sqlite3"
    assert build_index(csv_path, index) == 3
    provider = CombinedRecipeProvider(index)
    found = asyncio.run(provider.search("Beef"))
    assert len(found) == 1
    assert found[0].ingredients[0].quantity == 500
    assert found[0].ingredients[1].unit.value == "unit"
    assert asyncio.run(provider.get_by_id(found[0].id)) == found[0]
    assert asyncio.run(provider.search("Cup")) == []
    batch = asyncio.run(provider.search("Rice"))[0]
    assert batch.source == "recipenlg_batch"
    assert "1 lote" in batch.description


def test_registry_is_bounded():
    registry = RecipeRegistry(capacity=1)
    first = Recipe(id="first", name="First", servings=1, ingredients=[], instructions=[], source="test")
    second = first.model_copy(update={"id": "second"})
    registry.put(first)
    registry.put(second)
    assert registry.get("first") is None
    assert registry.get("second") == second
