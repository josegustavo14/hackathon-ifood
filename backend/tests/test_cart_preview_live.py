from fastapi.testclient import TestClient

from app.core.dependencies import get_ifood_gateway
from app.integrations.ifood.cart import CartDetails
from app.integrations.ifood.models import AddressListResponse, AvailabilityStatus, DeliveryAddress, ItemDetailsResult
from app.main import app
from app.mocks.data import products, recipe
from app.mocks.services import MockShoppingEngine


def test_real_cart_requires_review_and_revalidates_before_write(monkeypatch):
    sample = recipe()
    engine = MockShoppingEngine()
    matching = engine.match_products(engine.calculate(sample, sample.servings), products())
    assert matching.status.value == "ready_for_review"
    matching = matching.model_copy(update={"items": [item.model_copy(update={
        "selected_product": item.selected_product.model_copy(update={"source": "ifood_mcp"})
    }) for item in matching.items]})
    monkeypatch.setenv("MOCK_MODE", "false")

    class FakeGateway:
        writes = 0
        price_changed = False
        tools_available = True

        async def list_tools(self):
            return [{"name": "createCart"}] if self.tools_available else []

        async def list_addresses(self):
            return AddressListResponse(addresses=[DeliveryAddress(
                addressId="address-1", formattedAddress="Rua A, 10",
                coordinates={"latitude": -12.97, "longitude": -38.50},
            )])

        async def get_item(self, item_id, merchant_id, **kwargs):
            product = next(item.selected_product for item in matching.items if item.selected_product.id == item_id)
            return ItemDetailsResult(tool="getItem", data={}, item_id=item_id, merchant_id=merchant_id,
                                     name=product.name, price=product.price + (1 if self.price_changed else 0),
                                     availability=AvailabilityStatus.available)

        async def create_cart(self, merchant_id, address_id, items):
            self.writes += 1
            assert merchant_id == matching.items[0].selected_product.merchant_id
            assert address_id == "address-1"
            assert all(item.quantity > 0 and item.options == [] for item in items)
            return CartDetails(cartId="cart-1")

    fake = FakeGateway()

    async def fake_gateway():
        yield fake

    app.dependency_overrides[get_ifood_gateway] = fake_gateway
    try:
        with TestClient(app) as client:
          proposal_response = client.post("/api/v1/cart/preview", json={"shopping_list": matching.model_dump(mode="json"), "address_id": "address-1"})
          assert proposal_response.status_code == 200
          proposal = proposal_response.json()
          assert proposal["status"] == "ready_for_review"
          assert proposal["merchant_id"]
          assert proposal["address_id"] == "address-1"
          tampered = matching.model_dump(mode="json")
          tampered["estimated_subtotal"] = "0.00"
          assert client.post("/api/v1/cart/preview", json={"shopping_list": tampered, "address_id": "address-1"}).status_code == 409
          assert client.post("/api/v1/cart/preview", json={"shopping_list": matching.model_dump(mode="json")}).status_code == 422
          assert client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": False}).status_code == 409
          non_ifood = {**proposal, "items": [dict(item) for item in proposal["items"]]}
          non_ifood["items"][0]["selected_product"] = {**non_ifood["items"][0]["selected_product"], "source": "mock_ep00"}
          assert client.post("/api/v1/cart/apply", json={"proposal": non_ifood, "confirmed": True}).status_code == 409
          assert fake.writes == 0
          fake.tools_available = False
          apply_response = client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True})
          assert apply_response.status_code == 503
          assert fake.writes == 0
          fake.tools_available = True
          fake.price_changed = True
          assert client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True}).status_code == 409
          assert fake.writes == 0
          fake.price_changed = False
          applied = client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True})
          assert applied.status_code == 200
          assert applied.json()["mock_only"] is False
          assert applied.json()["cart_id"] == "cart-1"
          assert fake.writes == 1
    finally:
        app.dependency_overrides.pop(get_ifood_gateway, None)
