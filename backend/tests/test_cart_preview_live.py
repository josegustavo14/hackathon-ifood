from fastapi.testclient import TestClient

from app.main import app
from app.mocks.data import products, recipe
from app.mocks.services import MockShoppingEngine


def test_real_mode_only_previews_cart_and_never_writes(monkeypatch):
    sample = recipe()
    engine = MockShoppingEngine()
    matching = engine.match_products(engine.calculate(sample, sample.servings), products())
    assert matching.status.value == "ready_for_review"
    monkeypatch.setenv("MOCK_MODE", "false")
    with TestClient(app) as client:
        proposal_response = client.post("/api/v1/cart/preview", json={"shopping_list": matching.model_dump(mode="json")})
        assert proposal_response.status_code == 200
        proposal = proposal_response.json()
        assert proposal["status"] == "ready_for_review"
        assert proposal["merchant_id"]
        tampered = matching.model_dump(mode="json")
        tampered["estimated_subtotal"] = "0.00"
        assert client.post("/api/v1/cart/preview", json={"shopping_list": tampered}).status_code == 409
        apply_response = client.post("/api/v1/cart/apply", json={"proposal": proposal, "confirmed": True})
        assert apply_response.status_code == 503
        assert "no real cart was changed" in apply_response.json()["error"]["message"]
