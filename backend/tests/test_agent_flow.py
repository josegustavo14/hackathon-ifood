from fastapi.testclient import TestClient
import asyncio
import httpx

from app.agent.service import AgentService
from app.core.dependencies import get_recipe_provider
from app.integrations.recipes.provider import CombinedRecipeProvider, registry
from app.main import app
from app.mocks.data import recipe as mock_recipe
from app.models.agent import AgentRequest, AgentResponse, AgentStatus


def test_generated_recipe_is_available_to_shopping(monkeypatch):
    generated = mock_recipe().model_copy(update={"id": "llm-generated-test", "source": "llm_web"})

    async def fake_web(self, query):
        return generated

    monkeypatch.setattr(AgentService, "_web_recipe", fake_web)
    app.dependency_overrides[get_recipe_provider] = CombinedRecipeProvider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/agent/chat", json={"message": "Quero preparar uma lasanha"})
            assert response.status_code == 200
            assert response.json()["nutrition"] is None
            assert response.json()["nutrition_requested"] is False
            assert client.get("/api/v1/recipes/llm-generated-test").status_code == 200
            assert client.post("/api/v1/shopping/calculate", json={"recipe_id": "llm-generated-test", "servings": 4}).status_code == 200
    finally:
        app.dependency_overrides.pop(get_recipe_provider, None)
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


def test_requested_macros_explain_missing_recipenlg_data(monkeypatch):
    sample = mock_recipe().model_copy(update={"id": "recipenlg-42", "source": "recipenlg_batch", "servings": 1})

    async def fake_chat(self, request):
        return AgentResponse(session_id="session-1", message="Encontrei uma receita.",
                             status=AgentStatus.completed, recipe=sample, nutrition_requested=True)

    monkeypatch.setattr(AgentService, "chat", fake_chat)
    monkeypatch.setenv("NUTRITION_PROVIDER", "mock")
    with TestClient(app) as client:
        response = client.post("/api/v1/agent/chat", json={"message": "Calcule os macros"})
    assert response.status_code == 200
    assert response.json()["nutrition"] is None
    assert "fonte nutricional demonstrativa" in response.json()["message"]
    assert "lote completo" in response.json()["message"]


def test_llm_can_identify_implicit_nutrition_intent(monkeypatch):
    original_client = httpx.AsyncClient

    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"nutrition_requested": true}'}}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    service = AgentService(provider="openai_compatible", api_key="test", model="test")
    assert asyncio.run(service._nutrition_intent("Quero saber o impacto disso na minha dieta")) is True


def test_unconverted_llm_recipe_returns_agent_error_not_http_500(monkeypatch):
    original_client = httpx.AsyncClient

    def handler(request):
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"nutrition_requested": false}'}}]})
        return httpx.Response(200, json={"output_text": '{"name":"Cake","servings":4,"ingredients":[{"name":"flour","quantity":1,"unit":"cup"}],"instructions":["Bake"],"source_url":"https://example.com"}'})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler)))
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "test")
    monkeypatch.setenv("LLM_MODEL", "test")
    app.dependency_overrides[get_recipe_provider] = CombinedRecipeProvider
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/agent/chat", json={"message": "Quero fazer bolo"})
            assert response.status_code == 200
            assert response.json()["status"] == "error"
    finally:
        app.dependency_overrides.pop(get_recipe_provider, None)
