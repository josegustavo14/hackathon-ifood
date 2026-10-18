import asyncio
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_nutrition_provider
from app.integrations.recipes.provider import CombinedRecipeProvider, registry
from app.main import app
from app.mocks.data import recipe as mock_recipe, load_json
from app.mocks.services import MockNutritionProvider
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe, MealPlan
from app.models.nutrition import NutritionStatus
from app.nutrition.usda import (
    USDAClient,
    USDAIngredientMapping,
    USDANutritionProvider,
    USDAUpstreamError,
    USDAFoodCache,
    ingredient_mappings,
    ingredient_grams,
    nutrient_values,
)

FOODS = json.loads((Path(__file__).parent / "fixtures" / "usda_foods.json").read_text(encoding="utf-8"))
LIVE_FOODS = json.loads((Path(__file__).parent / "fixtures" / "usda_live_foods.json").read_text(encoding="utf-8"))


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


def test_pasta_with_verified_usda_records_has_macros_extras_and_breakdown():
    sample = Recipe.model_validate(load_json("pasta.json"))
    result = calculate_with(LIVE_FOODS, recipe=sample)
    assert result.status == NutritionStatus.complete
    assert result.total.calories_kcal == Decimal("3392.00")
    assert result.per_serving.calories_kcal == Decimal("848.00")
    assert result.per_serving.protein_g == Decimal("41.92")
    assert result.per_serving.carbohydrates_g == Decimal("99.15")
    assert result.per_serving.fat_g == Decimal("30.41")
    assert result.per_serving.fiber_g == Decimal("5.13")
    assert result.per_serving.sodium_mg == Decimal("134.25")
    assert len(result.sources) == 4
    assert result.sources[2].nutrients["calories_kcal"] == Decimal("390.00")
    doubled = calculate_with(LIVE_FOODS, recipe=sample, servings=8)
    assert doubled.total.calories_kcal == result.total.calories_kcal * 2
    assert doubled.per_serving == result.per_serving


def test_standard_recipe_can_be_calculated_after_registry_reset():
    registry._recipes.pop("demo-macarrao-cremoso", None)
    sample = asyncio.run(CombinedRecipeProvider().get_by_id("demo-macarrao-cremoso"))
    assert sample is not None
    assert calculate_with(LIVE_FOODS, recipe=sample).status == NutritionStatus.complete


def test_additional_nutrient_is_omitted_if_one_ingredient_has_no_value():
    records = deepcopy(LIVE_FOODS)
    records["170857"]["foodNutrients"] = [n for n in records["170857"]["foodNutrients"] if n["nutrient"]["id"] != 1093]
    result = calculate_with(records, recipe=Recipe.model_validate(load_json("pasta.json")))
    assert result.status == NutritionStatus.complete
    assert result.total.sodium_mg is None
    assert result.total.fiber_g == Decimal("20.50")


def test_unknown_yield_has_total_without_inventing_per_serving_values():
    sample = Recipe.model_validate(load_json("pasta.json")).model_copy(update={"source": "recipenlg_batch", "servings": 1})
    result = calculate_with(LIVE_FOODS, recipe=sample, servings=1)
    assert result.status == NutritionStatus.complete
    assert result.total.calories_kcal == Decimal("3392.00")
    assert result.per_serving is None
    assert result.serving_yield_known is False


def test_household_measure_does_not_become_one_whole_egg():
    egg = Ingredient(id="egg", name="Ovo", quantity="1", unit="unit", notes="medida caseira original: xícara")
    result = ingredient_grams(egg, 1, 1, ingredient_mappings()["ovo"], LIVE_FOODS["171287"])
    assert result is None
    whole = egg.model_copy(update={"notes": None})
    assert ingredient_grams(whole, 1, 1, ingredient_mappings()["ovo"], LIVE_FOODS["171287"]) == Decimal("50")


def test_usda_cache_reuses_records_and_does_not_cache_failed_requests(monkeypatch):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=LIVE_FOODS["170857"])
    cache = USDAFoodCache()
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            first = await USDAClient("test-key", http, cache).get_food(170857)
            first["description"] = "mutated"
            second = await USDAClient("test-key", http, cache).get_food(170857)
            assert second["description"] == LIVE_FOODS["170857"]["description"]
    asyncio.run(run())
    assert len(requests) == 1
    cache.ttl_seconds = 0
    asyncio.run(run())
    assert len(requests) == 3
    async def failed():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as http:
            with pytest.raises(USDAUpstreamError):
                await USDAClient("test-key", http, cache).get_food(170857)
    asyncio.run(failed())
    assert cache.get(170857) is None


def test_cache_is_bounded():
    cache = USDAFoodCache(capacity=1)
    cache.put(1, {"fdcId": 1})
    cache.put(2, {"fdcId": 2})
    assert cache.get(1) is None
    assert cache.get(2) == {"fdcId": 2}


def test_cache_survives_restart_and_keeps_original_expiry(tmp_path):
    from time import time
    path = tmp_path / "usda.sqlite3"
    first = USDAFoodCache(path=path)
    first.put(170857, LIVE_FOODS["170857"])
    second = USDAFoodCache(path=path)
    assert second.get(170857)["description"] == LIVE_FOODS["170857"]["description"]
    first.put(170857, LIVE_FOODS["170857"], fetched_at=time() - 90000)
    assert USDAFoodCache(path=path).get(170857) is None


def test_nutrition_chat_uses_selected_servings_and_returns_full_calculation(monkeypatch):
    async def fake_provider():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response_handler(LIVE_FOODS))) as http:
            yield USDANutritionProvider(USDAClient("test-key", http))
    monkeypatch.setattr("app.api.v1.agent.get_nutrition_provider", fake_provider)
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/agent/chat", json={"message": "Quero macarrão e as calorias", "context": {"servings": 2}}).json()
            assert result["nutrition_calculation"]["status"] == "complete"
            assert result["nutrition_calculation"]["servings"] == 2
            assert result["nutrition_calculation"]["total"]["calories_kcal"] == "1696.00"
            assert result["nutrition"]["calories_kcal"] == "848.00"
    finally:
        app.dependency_overrides.pop(get_nutrition_provider, None)


def test_meal_plan_nutrition_counts_weekly_frequency(monkeypatch):
    plan = MealPlan.model_validate({
        "id": "weekly-rice", "source_filename": "plan.pdf", "days": ["Segunda"],
        "meals": [{"day": "Segunda", "name": "Almoço", "frequency_per_week": 7,
                   "ingredients": [{"id": "rice", "name": "Arroz", "quantity": "100", "unit": "g"}]}],
    })
    async def parsed(*args, **kwargs):
        return plan
    monkeypatch.setattr("app.api.v1.agent.extract_text", lambda content: "text")
    monkeypatch.setattr("app.api.v1.agent.interpret_meal_plan", parsed)
    async def fake_provider():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response_handler(LIVE_FOODS))) as http:
            yield USDANutritionProvider(USDAClient("test-key", http))
    monkeypatch.setattr("app.api.v1.agent.get_nutrition_provider", fake_provider)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/meal-plans/parse", files={"file": ("plan.pdf", b"%PDF-1.4", "application/pdf")})
            assert response.status_code == 200
            data = response.json()
            assert data["nutrition"]["sources"][0]["grams"] == "700"
            assert data["nutrition"]["total"]["calories_kcal"] == "2555.00"
            assert data["nutrition"]["per_serving"] is None
    finally:
        app.dependency_overrides.pop(get_nutrition_provider, None)


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
