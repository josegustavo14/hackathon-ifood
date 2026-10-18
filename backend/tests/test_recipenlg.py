import asyncio
import csv
import zipfile
from pathlib import Path
import httpx

from app.integrations.recipes.provider import CombinedRecipeProvider, RecipeRegistry
from app.integrations.recipes.recipenlg import _ingredient, build_index
from app.integrations.recipes.index_recipes import extract_csv
from app.integrations.recipes.localize import localize_recipe
from app.integrations.recipes import RecipeProviderError, normalize_recipe
from app.models.recipe import Recipe
import pytest


def test_local_recipenlg_index_and_safe_normalization(tmp_path: Path):
    csv_path = tmp_path / "full_dataset.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["title", "ingredients", "directions", "link", "source", "servings"])
        writer.writeheader()
        writer.writerow({"title": "Beef Stew", "ingredients": "['500 g beef', '2 onions']", "directions": "['Cook the beef.', 'Add onions.']", "link": "https://example.com/stew", "source": "Gathered", "servings": "4"})
        writer.writerow({"title": "Cup Cake", "ingredients": "['1 cup flour']", "directions": "['Bake.']", "source": "Gathered", "servings": "4"})
        writer.writerow({"title": "Rice Bowl", "ingredients": "['250 g rice', '2 eggs']", "directions": "['Cook rice.']", "source": "Gathered"})
        writer.writerow({"title": "Lasagna", "ingredients": "['500 g pasta', '300 g cheese']", "directions": "['Bake.']", "source": "Gathered"})
        writer.writerow({"title": "Old Beef", "ingredients": "['500 g beef']", "directions": "['Cook.']", "source": "Recipes1M", "servings": "4"})
    index = tmp_path / "recipes.sqlite3"
    assert build_index(csv_path, index) == 4
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
    assert asyncio.run(provider.search("lasanha"))[0].name == "Lasagna"


@pytest.mark.parametrize("raw", ["1 lb. ground beef", "1 c. mozzarella", "2 jars sauce", "1 (16 ounce) package noodles", "3 tbsp oil", "2 1/2 lb. cheese", "1 small box noodles", "1 medium-size container ricotta", "1 recipe for sauce"])
def test_unsupported_recipe_measures_are_not_item_counts(raw: str):
    assert _ingredient(raw, 1) is None


def test_registry_is_bounded():
    registry = RecipeRegistry(capacity=1)
    first = Recipe(id="first", name="First", servings=1, ingredients=[], instructions=[], source="test")
    second = first.model_copy(update={"id": "second"})
    registry.put(first)
    registry.put(second)
    assert registry.get("first") is None
    assert registry.get("second") == second


def test_zip_extracts_only_dataset_csv_and_keeps_index_on_invalid_reimport(tmp_path: Path):
    archive = tmp_path / "dataset.zip"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("nested/full_dataset.csv", "title,ingredients,directions,source\nSoup,\"['100 g lentils', '200 ml water']\",\"['Cook.']\",Gathered\n")
    csv_path = extract_csv(archive)
    assert csv_path == tmp_path / "full_dataset.csv"
    index = tmp_path / "index.sqlite3"
    assert build_index(csv_path, index) == 1
    csv_path.write_text("wrong,header\n1,2\n")
    with pytest.raises(RecipeProviderError):
        build_index(csv_path, index)
    provider = CombinedRecipeProvider(index)
    assert asyncio.run(provider.search("Soup"))[0].name == "Soup"


def test_llm_recipe_rejects_unconverted_or_missing_ingredients():
    payload = {"name": "Cake", "servings": 4, "ingredients": [{"name": "flour", "quantity": 1, "unit": "cup"}], "instructions": ["Bake."]}
    with pytest.raises(RecipeProviderError):
        normalize_recipe(payload, source="llm_web")
    payload["ingredients"] = [{"name": "flour", "quantity": 500, "unit": "g"}]
    assert normalize_recipe(payload, source="llm_web").ingredients[0].quantity == 500
    payload["ingredients"] = [{"name": "egg", "quantity": 2, "unit": "unit"}]
    assert normalize_recipe(payload, source="llm_web").ingredients[0].unit.value == "unit"


def test_localization_changes_only_labels(monkeypatch):
    recipe = Recipe(id="recipenlg-1", name="Rice", servings=1, ingredients=[
        {"id": "rice-1", "name": "rice", "quantity": "250", "unit": "g"}],
        instructions=["Boil rice."], source="recipenlg_batch")
    original_client = httpx.AsyncClient

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"Arroz","ingredients":[{"id":"rice-1","name":"arroz"}]}'}}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    translated = asyncio.run(localize_recipe(recipe, api_key="test", model="test", base_url="https://example.test/v1", timeout=5))
    assert translated.name == "Arroz"
    assert translated.ingredients[0].name == "arroz"
    assert translated.ingredients[0].quantity == recipe.ingredients[0].quantity
    assert translated.id == recipe.id and translated.instructions == recipe.instructions
