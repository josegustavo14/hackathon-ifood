import asyncio
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_nutrition_provider
from app.main import app
from app.mocks.data import recipe as mock_recipe
from app.mocks.services import MockNutritionProvider
from app.models.ingredient import Ingredient
from app.models.nutrition import NutritionStatus
from app.nutrition.usda import (
    USDAClient,
    USDAIngredientMapping,
    USDANutritionProvider,
    USDAUpstreamError,
    ingredient_grams,
    nutrient_values,
)

FOODS = json.loads((Path(__file__).parent / "fixtures" / "usda_foods.json").read_text(encoding="utf-8"))


def response_handler(records, *, status=200):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.nal.usda.gov"
        assert request.url.params["api_key"] == "test-key"
        if status != 200:
            return httpx.Response(status)
        food = records.get(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json=food) if food else httpx.Response(404)
    return handle


def calculate_with(records, servings=4, recipe=None, include_optional=False):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response_handler(records))) as http:
            provider = USDANutritionProvider(USDAClient("test-key", http))
            return await provider.calculate(recipe or mock_recipe(), servings, include_optional)
    return asyncio.run(run())


def test_usda_recipe_total_and_portion():
    four = calculate_with(FOODS)
    eight = calculate_with(FOODS, servings=8)
    assert four.status == NutritionStatus.complete
    assert four.total.calories_kcal == Decimal("4326.94")
    assert four.per_serving.calories_kcal == Decimal("1081.74")
    assert eight.total.calories_kcal == Decimal("8653.88")
    assert eight.per_serving.calories_kcal == four.per_serving.calories_kcal
    assert {source.ingredient_id: source.grams for source in four.sources}["onion"] == Decimal("110")
    assert {source.ingredient_id: source.grams for source in four.sources}["garlic"] == Decimal("6")
    assert four.total.source == "USDA FoodData Central"
    assert four.total.estimated is True


def test_missing_data_never_becomes_zero_or_total():
    records = deepcopy(FOODS)
    records["169230"]["foodNutrients"] = [
        item for item in records["169230"]["foodNutrients"] if item["nutrient"]["id"] != 1003
    ]
    result = calculate_with(records)
    assert result.status == NutritionStatus.incomplete
    assert result.total is None and result.per_serving is None
    assert result.unresolved_ingredients[0].ingredient_id == "garlic"
    assert result.unresolved_ingredients[0].reason == "nutrients_missing"
    assert len(result.sources) == 5


def test_unmapped_and_optional_ingredients():
    extra = Ingredient(id="unknown", name="Ingrediente desconhecido", quantity="5", unit="g", optional=True)
    sample = mock_recipe().model_copy(update={"ingredients": [*mock_recipe().ingredients, extra]})
    excluded = calculate_with(FOODS, recipe=sample)
    included = calculate_with(FOODS, recipe=sample, include_optional=True)
    assert excluded.status == NutritionStatus.complete
    assert any("opcionais" in warning for warning in excluded.warnings)
    assert included.status == NutritionStatus.incomplete
    assert included.unresolved_ingredients[0].reason == "unmapped_ingredient"


def test_missing_portion_and_unit_conversions():
    records = deepcopy(FOODS)
    records["170000"]["foodPortions"] = []
    result = calculate_with(records)
    assert result.status == NutritionStatus.incomplete
    assert result.unresolved_ingredients[0].reason == "weight_conversion_unavailable"

    mapping = USDAIngredientMapping(aliases=["água"], fdc_id=1, expected_description="Water", density_g_per_ml="1.03")
    assert ingredient_grams(Ingredient(id="x", name="X", quantity="0.5", unit="kg"), 4, 4, mapping, {}) == Decimal("500")
    assert ingredient_grams(Ingredient(id="x", name="X", quantity="250", unit="ml"), 4, 4, mapping, {}) == Decimal("257.50")
    assert ingredient_grams(Ingredient(id="x", name="X", quantity="1", unit="l"), 4, 4, mapping, {}) == Decimal("1030.00")


def test_energy_precedence_and_real_zero():
    food = deepcopy(FOODS["171796"])
    food["foodNutrients"].extend([
        {"nutrient": {"id": 2047, "unitName": "kcal"}, "amount": 222},
        {"nutrient": {"id": 2048, "unitName": "kcal"}, "amount": 224},
    ])
    values = nutrient_values(food)
    assert values["calories_kcal"] == Decimal("224")
    assert values["carbohydrates_g"] == Decimal("0")
    food["foodNutrients"] = None
    assert nutrient_values(food) is None


@pytest.mark.parametrize("status,expected", [(429, 503), (401, 503), (500, 502)])
def test_usda_http_errors(status, expected):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response_handler(FOODS, status=status))) as http:
            with pytest.raises(USDAUpstreamError) as error:
                await USDAClient("test-key", http).get_food(170000)
            assert error.value.status_code == expected
    asyncio.run(run())


def test_usda_timeout_and_invalid_json():
    def timeout_handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout_handler)) as http:
            with pytest.raises(USDAUpstreamError) as error:
                await USDAClient("test-key", http).get_food(170000)
            assert error.value.status_code == 504
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not JSON"))) as http:
            with pytest.raises(USDAUpstreamError) as error:
                await USDAClient("test-key", http).get_food(170000)
            assert error.value.status_code == 502
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"fdcId": 170000}))) as http:
            with pytest.raises(USDAUpstreamError) as error:
                await USDAClient("test-key", http).get_food(170000)
            assert error.value.status_code == 502
    asyncio.run(run())


def test_missing_source_record_is_incomplete():
    records = deepcopy(FOODS)
    records.pop("170845")
    result = calculate_with(records)
    assert result.status == NutritionStatus.incomplete
    assert result.total is None
    assert result.unresolved_ingredients[0].ingredient_id == "cheese"
    assert result.unresolved_ingredients[0].reason == "source_record_unavailable"


def test_nutrition_mock_does_not_reuse_lasagna_values_for_another_recipe():
    other = mock_recipe().model_copy(update={"id": "different-recipe"})
    result = asyncio.run(MockNutritionProvider().calculate(other, 4))
    assert result.status == NutritionStatus.incomplete
    assert result.total is None and result.per_serving is None


def test_endpoint_with_fake_usda_and_missing_key(monkeypatch):
    async def fake_provider():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response_handler(FOODS))) as http:
            yield USDANutritionProvider(USDAClient("test-key", http))

    app.dependency_overrides[get_nutrition_provider] = fake_provider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/nutrition/calculate", json={"recipe_id": mock_recipe().id, "servings": 4})
            assert response.status_code == 200
            assert response.json()["total"]["calories_kcal"] == "4326.94"
            assert client.post("/api/v1/nutrition/calculate", json={"recipe_id": "absent", "servings": 4}).status_code == 404
            assert client.post("/api/v1/nutrition/calculate", json={"recipe_id": mock_recipe().id, "servings": 0}).status_code == 422
    finally:
        app.dependency_overrides.clear()

    monkeypatch.setenv("NUTRITION_PROVIDER", "usda")
    monkeypatch.delenv("USDA_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/nutrition/calculate", json={"recipe_id": mock_recipe().id, "servings": 4})
    assert response.status_code == 503
    assert "USDA_API_KEY" in response.json()["error"]["message"]
