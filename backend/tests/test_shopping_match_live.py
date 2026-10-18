from fastapi.testclient import TestClient

from app.core.dependencies import get_ifood_gateway
from app.integrations.ifood.models import AddressListResponse, DeliveryAddress
from app.main import app
from app.mocks.data import recipe
from app.shopping.engine import DeterministicShoppingEngine


def test_live_match_resolves_address_once_and_deduplicates_queries(monkeypatch):
    sample = recipe()
    shopping = DeterministicShoppingEngine().calculate(sample, sample.servings)
    first = shopping.items[0]
    repeated = first.model_copy(update={"ingredient": first.ingredient.model_copy(update={"id": "same-name-2"})})
    shopping = shopping.model_copy(update={"items": [first, repeated]})
    monkeypatch.setenv("MOCK_MODE", "false")

    class FakeGateway:
        address_calls = 0
        searches = []

        async def list_addresses(self):
            self.address_calls += 1
            return AddressListResponse(addresses=[DeliveryAddress(
                addressId="address-1", formattedAddress="Rua A, 10",
                coordinates={"latitude": -12.97, "longitude": -38.50},
            )])

        async def search_products(self, name, merchant_id, **kwargs):
            self.searches.append((name, kwargs))
            return []

    fake = FakeGateway()

    async def gateway_override():
        yield fake

    app.dependency_overrides[get_ifood_gateway] = gateway_override
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/shopping/match", json={
                "shopping_list": shopping.model_dump(mode="json"), "address_id": "address-1",
            })
            assert response.status_code == 200
            assert response.json()["status"] == "needs_review"
        assert fake.address_calls == 1
        assert len(fake.searches) == 1
        assert fake.searches[0][1]["latitude"] == -12.97
        assert fake.searches[0][1]["longitude"] == -38.50
    finally:
        app.dependency_overrides.pop(get_ifood_gateway, None)
