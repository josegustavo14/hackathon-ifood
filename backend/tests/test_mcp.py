"""Protocol-level tests against the actual FastAPI app, without external services."""

import base64

import httpx
import pytest

pytest.importorskip("mcp", reason="Install requirements-mcp.txt for MCP tests")

from mcp.shared.memory import create_connected_server_and_client_session
from app.main import app
from app.mcp_server.client import ChefAPI
from app.mcp_server.server import MAX_BASE64_CHARS, create_server
from app.mcp_server.smoke import sample_meal_plan_pdf


@pytest.fixture
def anyio_backend():
    return "asyncio"


class RecordingTransport(httpx.ASGITransport):
    def __init__(self):
        super().__init__(app=app)
        self.paths = []

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        return await super().handle_async_request(request)


@pytest.fixture
async def connected(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("NUTRITION_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    monkeypatch.delenv("RECIPENLG_INDEX_PATH", raising=False)
    transport = RecordingTransport()
    server = create_server(ChefAPI("http://testserver", transport))
    async with create_connected_server_and_client_session(server) as session:
        yield session, transport


async def call(session, name, **arguments):
    result = await session.call_tool(name, arguments)
    assert not result.isError, result.content
    data = result.structuredContent
    assert data is not None
    return data.get("result", data)


@pytest.mark.anyio
async def test_discovery_resources_prompt_and_schema(connected):
    session, _ = connected
    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
    assert len(tools) == 10
    assert tools["apply_cart"].annotations.readOnlyHint is False
    assert tools["apply_cart"].annotations.destructiveHint is True
    assert tools["apply_cart"].inputSchema["properties"]["confirmed"]["default"] is False
    assert tools["parse_meal_plan"].inputSchema["properties"]["pdf_base64"]["maxLength"] == MAX_BASE64_CHARS
    assert tools["calculate_nutrition"].outputSchema["properties"]["per_serving"]
    resources = await session.list_resources()
    assert str(resources.resources[0].uri) == "chef://guide"
    guide = await session.read_resource("chef://guide")
    assert "Não é o MCP oficial do iFood" in guide.contents[0].text
    prompt = await session.get_prompt("prepare_recipe", {"dish": "lasanha", "servings": "4"})
    assert "Não chame apply_cart" in prompt.messages[0].content.text


@pytest.mark.anyio
async def test_complete_recipe_to_cart_and_confirmation(connected):
    session, transport = connected
    assert (await call(session, "health"))["mock_mode"] is True
    recipes = await call(session, "search_recipes", query="lasanha")
    recipe = await call(session, "get_recipe", recipe_id=recipes[0]["id"])
    nutrition = await call(session, "calculate_nutrition", recipe_id=recipe["id"], servings=4)
    assert nutrition["total"]["calories_kcal"] == "3200"
    assert nutrition["per_serving"]["calories_kcal"] == "800"
    shopping = await call(session, "calculate_shopping", recipe_id=recipe["id"], servings=4)
    assert shopping["items"][0]["status"] == "pending"
    matched = await call(session, "match_products", shopping_list=shopping)
    assert matched["estimated_subtotal"] == "70.90"
    proposal = await call(session, "preview_cart", shopping_list=matched)
    assert proposal["requires_confirmation"] is True
    assert "/api/v1/cart/apply" not in transport.paths
    for extra in ({}, {"confirmed": False}, {"confirmed": "true"}, {"confirmed": 1}):
        rejected = await session.call_tool("apply_cart", {"proposal": proposal, **extra})
        assert rejected.isError
    assert "/api/v1/cart/apply" not in transport.paths
    applied = await call(session, "apply_cart", proposal=proposal, confirmed=True)
    assert applied["mock_only"] is True
    assert applied["proposal"]["status"] == "applied"
    assert transport.paths.count("/api/v1/cart/apply") == 1
    assert (await session.call_tool("apply_cart", {"proposal": applied["proposal"], "confirmed": True})).isError
    assert transport.paths.count("/api/v1/cart/apply") == 1


@pytest.mark.anyio
async def test_portions_pantry_and_unresolved_cart(connected):
    session, _ = connected
    recipes = await call(session, "search_recipes", query="lasanha")
    recipe = recipes[0]
    shopping = await call(session, "calculate_shopping", recipe_id=recipe["id"], servings=8,
                          pantry_ingredient_ids=[recipe["ingredients"][0]["id"]])
    assert len(shopping["items"]) == 5
    assert len(shopping["unresolved_ingredients"]) == 5
    from decimal import Decimal
    assert Decimal(shopping["items"][0]["ingredient"]["quantity"]) == Decimal(recipe["ingredients"][1]["quantity"]) * 2
    assert (await session.call_tool("preview_cart", {"shopping_list": shopping})).isError
    assert (await session.call_tool("calculate_shopping", {"recipe_id": recipe["id"], "pantry_ingredient_ids": ["typo"]})).isError
    empty = await call(session, "calculate_shopping", recipe_id=recipe["id"],
                       pantry_ingredient_ids=[i["id"] for i in recipe["ingredients"]])
    assert empty["items"] == []
    assert (await session.call_tool("preview_cart", {"shopping_list": empty})).isError


@pytest.mark.anyio
async def test_chat_and_pdf(connected):
    session, _ = connected
    first = await call(session, "chat", message="Quero lasanha")
    second = await call(session, "chat", message="Quatro pessoas", session_id=first["session_id"])
    assert second["session_id"] == first["session_id"]
    plan = await call(session, "parse_meal_plan", filename="plano.pdf", pdf_base64=base64.b64encode(sample_meal_plan_pdf()).decode())
    assert len(plan["meals"]) == 1
    assert plan["meals"][0]["ingredients"][0]["name"] == "aveia"
    assert plan["extraction_warnings"]
    for name, content in [("../plano.pdf", b"%PDF-1.4"), ("plano.txt", b"%PDF-1.4"), ("plano.pdf", b"not pdf")]:
        assert (await session.call_tool("parse_meal_plan", {"filename": name, "pdf_base64": base64.b64encode(content).decode()})).isError
    assert (await session.call_tool("parse_meal_plan", {"filename": "plano.pdf", "pdf_base64": "!!!"})).isError


@pytest.mark.anyio
async def test_validation_and_http_errors_are_tool_results(connected, monkeypatch):
    session, transport = connected
    for tool, arguments in [("get_recipe", {"recipe_id": "unknown"}),
                            ("get_recipe", {"recipe_id": "../../health"}),
                            ("calculate_shopping", {"recipe_id": "x", "servings": 0}),
                            ("chat", {"message": "   "})]:
        assert (await session.call_tool(tool, arguments)).isError
    monkeypatch.setenv("NUTRITION_PROVIDER", "usda")
    monkeypatch.setenv("USDA_API_KEY", "")
    result = await session.call_tool("calculate_nutrition", {"recipe_id": "mock-lasagna-bolognese"})
    assert result.isError
    assert "503" in result.content[0].text


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["connection", "timeout", "invalid_json", "invalid_contract"])
async def test_upstream_failures(failure):
    def handler(request):
        if failure == "connection":
            raise httpx.ConnectError("private diagnostic", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private diagnostic", request=request)
        if failure == "invalid_json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"unrelated": "data"})

    server = create_server(ChefAPI("http://testserver", httpx.MockTransport(handler)))
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("health", {})
        assert result.isError
        assert "private diagnostic" not in result.content[0].text


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:secret@localhost", "http://localhost/api/v1", "http://localhost?q=x"])
def test_rejects_unsafe_api_configuration(url):
    with pytest.raises(ValueError):
        ChefAPI(url)
