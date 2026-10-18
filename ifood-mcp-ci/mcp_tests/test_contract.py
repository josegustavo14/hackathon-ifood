import asyncio
import json

import httpx
import pytest

from app.integrations.ifood.auth import OAuthTokenStore, OAuthTokens
from app.integrations.ifood.mcp import (
    MCPAuthenticationError,
    MCPError,
    StreamableHTTPMCPClient,
)
from app.integrations.ifood.settings import IFoodMCPSettings
from mcp_tests.auth_session import OAuthSessionUnavailable, get_valid_access_token


def _settings(token: str | None = "access-secret") -> IFoodMCPSettings:
    return IFoodMCPSettings(
        mcp_url="https://mcp.example.test/mcp",
        authorize_url="https://auth.example.test/authorize",
        redirect_uri="https://app.example.test/oauth/callback",
        client_id="client-id",
        client_secret="client-secret",
        token_url="https://auth.example.test/token",
        revoke_url="https://auth.example.test/revoke",
        access_token=token,
        scope=None,
        timeout_seconds=2,
        session_cookie_max_age_seconds=3600,
    )


@pytest.mark.contract
def test_initialize_bearer_session_and_tool_call_contract():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "mcp-session"},
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"capabilities": {}}},
            )
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"structuredContent": {"results": []}},
            },
        )

    async def run():
        client = StreamableHTTPMCPClient(_settings(), transport=httpx.MockTransport(handler))
        try:
            return await client.call_tool("ifood_listAddresses", {})
        finally:
            await client.aclose()

    assert asyncio.run(run()) == {"results": []}
    bodies = [json.loads(request.content) for request in requests]
    assert [body["method"] for body in bodies] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert requests[0].headers["authorization"] == "Bearer access-secret"
    assert requests[-1].headers["mcp-session-id"] == "mcp-session"
    assert bodies[0]["id"] != bodies[-1]["id"]


@pytest.mark.contract
def test_expiring_token_is_refreshed_and_rotated_pair_is_persisted():
    store = OAuthTokenStore()
    store.put(
        "browser-session",
        OAuthTokens(
            access_token="old-access",
            refresh_token="old-refresh",
            token_type="Bearer",
            expires_in=60,
            granted_scopes=frozenset({"mcp.user.basic.read"}),
        ),
    )
    refresh_calls: list[str] = []

    async def refresh(settings: IFoodMCPSettings, refresh_token: str) -> OAuthTokens:
        refresh_calls.append(refresh_token)
        return OAuthTokens(
            access_token="new-access",
            refresh_token="new-refresh",
            token_type="Bearer",
            expires_in=3600,
        )

    token = asyncio.run(
        get_valid_access_token("browser-session", store, _settings(), refresh=refresh)
    )

    assert token == "new-access"
    assert refresh_calls == ["old-refresh"]
    persisted = store.get("browser-session")
    assert persisted is not None
    assert persisted.refresh_token == "new-refresh"
    assert persisted.granted_scopes == frozenset({"mcp.user.basic.read"})


@pytest.mark.contract
def test_session_without_authorization_is_rejected():
    with pytest.raises(OAuthSessionUnavailable, match="not authorized"):
        asyncio.run(get_valid_access_token("missing", OAuthTokenStore(), _settings()))


@pytest.mark.contract
def test_http_and_json_rpc_errors_do_not_leak_secrets(capsys, caplog):
    responses = iter(
        [
            httpx.Response(401),
            httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "wrong-id",
                    "error": {"code": -32601, "message": "unknown tool"},
                },
            ),
        ]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return next(responses)

    async def run():
        first = StreamableHTTPMCPClient(_settings(), transport=httpx.MockTransport(handler))
        with pytest.raises(MCPAuthenticationError):
            await first.list_tools()
        await first.aclose()

        second = StreamableHTTPMCPClient(_settings(), transport=httpx.MockTransport(handler))
        with pytest.raises(MCPError, match="unknown tool"):
            await second.list_tools()
        await second.aclose()

    asyncio.run(run())
    captured = capsys.readouterr()
    observable_output = captured.out + captured.err + caplog.text
    assert "access-secret" not in observable_output
    assert "client-secret" not in observable_output
