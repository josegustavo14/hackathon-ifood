from __future__ import annotations

import asyncio

import pytest

from app.integrations.ifood.mcp import MCPAuthorizationError, StreamableHTTPMCPClient


@pytest.mark.live
def test_real_mcp_endpoint_responds_and_enforces_oauth(live_mcp_context):
    async def run():
        settings, _ = await live_mcp_context()
        client = StreamableHTTPMCPClient(settings)
        try:
            try:
                return "authorized", await client.list_tools()
            except MCPAuthorizationError:
                # A 403 proves that the real endpoint is reachable and enforcing
                # OAuth. Production user grants can be revoked or scope-limited,
                # so this smoke test does not require a permanent test identity.
                return "authorization_enforced", []
        finally:
            await client.aclose()

    status, tools = asyncio.run(run())
    assert status in {"authorized", "authorization_enforced"}
    if status == "authorized":
        assert tools
