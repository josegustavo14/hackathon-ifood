from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.dependencies import get_ifood_gateway
from app.integrations.ifood.models import AddressListResponse, AvailabilityStatus, DeliveryAddress, ItemDetailsResult
from app.main import app
from app.models.ingredient import Ingredient
from app.models.product import ProductCandidate
from app.models.recipe import Recipe
from app.shopping.engine import DeterministicShoppingEngine


def test_manual_catalog_choice_recalculates_proposal_without_writing_cart(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    recipe = Recipe(id="produce", name="Legumes", servings=1, source="test", instructions=[], ingredients=[
        Ingredient(id="carrot", name="Cenoura", quantity="1", unit="unit"),
        Ingredient(id="tomato", name="Tomate picado", quantity="2", unit="unit"),
    ])
    shopping = DeterministicShoppingEngine().calculate(recipe, 1)
    catalog = [
        ProductCandidate(id="carrot-a", merchant_id="market-a", name="Cenoura 500g", price="6.99",
                         package_quantity="500", package_unit="g", available=True, source="ifood_mcp"),
        ProductCandidate(id="tomato-a", merchant_id="market-a", name="Tomate 300g", price="4.50",
                         package_quantity="300", package_unit="g", available=True, source="ifood_mcp"),
        ProductCandidate(id="tomato-b", merchant_id="market-b", name="Tomate 500g", price="4.00",
                         package_quantity="500", package_unit="g", available=True, source="ifood_mcp"),
    ]

    class FakeGateway:
        writes = 0

        async def list_addresses(self):
            return AddressListResponse(addresses=[DeliveryAddress(
                addressId="address-1", formattedAddress="Rua A, 10",
                coordinates={"latitude": -12.97, "longitude": -38.50},
            )])

        async def search_products(self, query, merchant_id, **kwargs):
            return [product for product in catalog if product.name.casefold().startswith(query.casefold())]

        async def get_item(self, item_id, merchant_id, **kwargs):
            product = next(product for product in catalog if product.id == item_id)
            return ItemDetailsResult(tool="getItem", data={}, item_id=item_id, merchant_id=merchant_id,
                                     name=product.name, price=product.price,
                                     availability=AvailabilityStatus.available)

        async def create_cart(self, *args, **kwargs):
            self.writes += 1
            raise AssertionError("manual selection must not create a cart")

    fake = FakeGateway()

    async def gateway_override():
        yield fake

    app.dependency_overrides[get_ifood_gateway] = gateway_override
    try:
        with TestClient(app) as client:
            match = client.post("/api/v1/shopping/match", json={
                "shopping_list": shopping.model_dump(mode="json"), "address_id": "address-1",
            })
            assert match.status_code == 200
            list_data = match.json()
            assert [item["status"] for item in list_data["items"]] == ["needs_review", "needs_review"]
            assert len(list_data["items"][1]["suggested_products"]) == 2

            first = client.post("/api/v1/shopping/select-product", json={
                "shopping_list": list_data, "ingredient_id": "carrot", "product_id": "carrot-a",
                "purchase_quantity": 2, "address_id": "address-1",
            })
            assert first.status_code == 200
            list_data = first.json()
            assert list_data["estimated_subtotal"] == "13.98"
            assert list_data["status"] == "needs_review"

            cross_market = client.post("/api/v1/shopping/select-product", json={
                "shopping_list": list_data, "ingredient_id": "tomato", "product_id": "tomato-b",
                "purchase_quantity": 1, "address_id": "address-1",
            })
            assert cross_market.status_code == 409
            invalid_count = client.post("/api/v1/shopping/select-product", json={
                "shopping_list": list_data, "ingredient_id": "tomato", "product_id": "tomato-a",
                "purchase_quantity": 0, "address_id": "address-1",
            })
            assert invalid_count.status_code == 422

            second = client.post("/api/v1/shopping/select-product", json={
                "shopping_list": list_data, "ingredient_id": "tomato", "product_id": "tomato-a",
                "purchase_quantity": 1, "address_id": "address-1",
            })
            assert second.status_code == 200
            list_data = second.json()
            assert list_data["estimated_subtotal"] == "18.48"
            assert list_data["status"] == "ready_for_review"
            assert list_data["unresolved_ingredients"] == []
            assert list_data["items"][1]["reason"] == "manually_selected_unverified_quantity"
            preview = client.post("/api/v1/cart/preview", json={
                "shopping_list": list_data, "address_id": "address-1",
            })
            assert preview.status_code == 200
            assert Decimal(preview.json()["estimated_subtotal"]) == Decimal("18.48")
            assert fake.writes == 0

            skipped = client.post("/api/v1/shopping/skip-ingredient", json={
                "shopping_list": match.json(), "ingredient_id": "carrot",
            })
            assert skipped.status_code == 200
            assert [item["ingredient"]["id"] for item in skipped.json()["items"]] == ["tomato"]
            assert skipped.json()["status"] == "needs_review"
            assert client.post("/api/v1/shopping/skip-ingredient", json={
                "shopping_list": list_data, "ingredient_id": "carrot",
            }).status_code == 409
    finally:
        app.dependency_overrides.pop(get_ifood_gateway, None)
