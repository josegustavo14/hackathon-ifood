from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models.ingredient import Ingredient
from app.models.product import ProductCandidate
from app.models.recipe import Recipe

client = TestClient(app)


def test_startup_health_and_openapi():
    assert app.title == "iFood Chef AI API"
    assert client.get("/health").json() == {"status": "ok", "mock_mode": True}
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/cart/apply" in paths
    assert "/api/v1/meal-plans/parse" in paths


def test_recipes():
    results = client.get("/api/v1/recipes/search", params={"q": "lasanha"})
    assert results.status_code == 200
    recipe = results.json()[0]
    assert recipe["servings"] == 4
    assert len(recipe["ingredients"]) == 6
    assert client.get(f"/api/v1/recipes/{recipe['id']}").json() == recipe
    assert client.get("/api/v1/recipes/unknown").status_code == 404


def test_schema_validation_and_serialization():
    with pytest.raises(ValidationError):
        Ingredient(id="x", name="X", quantity="0", unit="cup")
    with pytest.raises(ValidationError):
        Recipe(id="x", name="X", servings=0, ingredients=[], instructions=[], source="mock")
    with pytest.raises(ValidationError):
        ProductCandidate(id="x", merchant_id="m", name="X", price="2.00", currency="USD", available=True, source="mock")
    product = ProductCandidate(id="x", merchant_id="m", name="X", price=Decimal("2.50"), available=True, source="mock")
    assert product.model_dump(mode="json")["price"] == "2.50"
    nutrition = client.post("/api/v1/nutrition/calculate", json={"recipe_id": "mock-lasagna-bolognese", "servings": 4}).json()
    assert nutrition["status"] == "complete"
    assert nutrition["total"]["calories_kcal"] == "3200"
    assert nutrition["per_serving"]["calories_kcal"] == "800"
    assert nutrition["per_serving"]["basis"] == "per_serving"
    assert nutrition["per_serving"]["estimated"] is True
    assert nutrition["per_serving"]["source"] == "mock_ep00"
    doubled = client.post("/api/v1/nutrition/calculate", json={"recipe_id": "mock-lasagna-bolognese", "servings": 8}).json()
    assert doubled["total"]["calories_kcal"] == "6400"
    assert doubled["per_serving"]["calories_kcal"] == "800"


def test_shopping_to_cart_mock_flow():
    shopping = client.post("/api/v1/shopping/calculate", json={"recipe_id": "mock-lasagna-bolognese", "servings": 4}).json()
    assert shopping["items"][0]["status"] == "pending"
    matched = client.post("/api/v1/shopping/match", json={"shopping_list": shopping}).json()
    assert matched["estimated_subtotal"] == "67.90"
    assert matched["unresolved_ingredients"] == []
    assert matched["items"][2]["purchase_quantity"] == 2
    proposal = client.post("/api/v1/cart/preview", json={"shopping_list": matched}).json()
    assert proposal["status"] == "ready_for_review"
    assert proposal["requires_confirmation"] is True
    rejected = client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": False})
    assert rejected.status_code == 409
    applied = client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True}).json()
    assert applied["mock_only"] is True
    assert applied["proposal"]["status"] == "applied"
    assert "no real iFood cart" in applied["message"]


def test_bad_inputs_and_pdf_mock():
    invalid = client.post("/api/v1/shopping/calculate", json={"recipe_id": "mock-lasagna-bolognese", "servings": 0})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert client.post("/api/v1/agent/chat", json={"message": " "}).status_code == 422
    assert client.post("/api/v1/meal-plans/parse", files={"file": ("x.txt", BytesIO(b"hello"), "text/plain")}).status_code == 400
    plan = client.post("/api/v1/meal-plans/parse", files={"file": ("plan.pdf", BytesIO(b"%PDF-1.4\nmock"), "application/pdf")}).json()
    assert len(plan["meals"]) == 4
    assert len(plan["meals"][0]["alternative_groups"][0]["options"]) == 2
    assert plan["extraction_warnings"]


def test_no_real_checkout_in_mock_mode(monkeypatch):
    from app.mocks.services import MockIFoodGateway

    async def forbidden(*args, **kwargs):
        raise AssertionError("Real checkout path was called")

    monkeypatch.setattr(MockIFoodGateway, "apply_cart", forbidden)
    shopping = client.post("/api/v1/shopping/calculate", json={"recipe_id": "mock-lasagna-bolognese", "servings": 4}).json()
    matched = client.post("/api/v1/shopping/match", json={"shopping_list": shopping}).json()
    proposal = client.post("/api/v1/cart/preview", json={"shopping_list": matched}).json()
    assert client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True}).status_code == 200
