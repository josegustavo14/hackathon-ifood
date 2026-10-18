from fastapi.testclient import TestClient

from app.agent.service import AgentService
from app.integrations.recipes.provider import registry
from app.main import app
from app.mocks.data import recipe as mock_recipe
from app.models.agent import AgentRequest


def test_generated_recipe_is_available_to_shopping(monkeypatch):
    generated = mock_recipe().model_copy(update={"id": "llm-generated-test", "source": "llm_web"})

    async def fake_web(self, query):
        return generated

    monkeypatch.setattr(AgentService, "_web_recipe", fake_web)
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/chat", json={"message": "Quero preparar uma lasanha"})
        assert response.status_code == 200
        assert response.json()["nutrition"] is None
        assert response.json()["nutrition_requested"] is False
        assert client.get("/api/v1/recipes/llm-generated-test").status_code == 200
        assert client.post("/api/v1/shopping/calculate", json={"recipe_id": "llm-generated-test", "servings": 4}).status_code == 200
    registry._recipes.pop("llm-generated-test", None)


def test_nutrition_only_on_explicit_request(monkeypatch):
    generated = mock_recipe().model_copy(update={"id": "nutrition-intent-test", "source": "llm_web"})

    async def fake_web(self, query):
        return generated

    monkeypatch.setattr(AgentService, "_web_recipe", fake_web)
    with TestClient(app) as client:
        result = client.post("/api/v1/agent/chat", json={"message": "Quero preparar uma lasanha e ver as calorias"}).json()
        assert result["nutrition_requested"] is True
        assert result["nutrition"] is None  # mock nutrition never invents values for generated recipes
        followup = client.post("/api/v1/agent/chat", json={"message": "E as proteínas?", "context": {"recipe_id": generated.id}}).json()
        assert followup["nutrition_requested"] is True
        assert followup["recipe"]["id"] == generated.id
    registry._recipes.pop("nutrition-intent-test", None)


def test_nutrition_intent_accents():
    assert AgentService.wants_nutrition("Quero informação nutricional")
    assert AgentService.wants_nutrition("Quantos macronutrientes tem?")
    assert not AgentService.wants_nutrition("Quero uma lasanha para jantar")
