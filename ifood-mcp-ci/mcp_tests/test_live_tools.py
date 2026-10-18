from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.integrations.ifood.mcp import StreamableHTTPMCPClient

TOOLS_DIRECTORY = Path(__file__).with_name("tools")


def _tool_cases() -> list[pytest.param]:
    cases: list[pytest.param] = []
    for path in sorted(TOOLS_DIRECTORY.glob("*.json")):
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise pytest.UsageError(f"{path.name} must contain a JSON object")
        tool = payload.get("tool")
        body = payload.get("body")
        if not isinstance(tool, str) or not tool or not isinstance(body, dict):
            raise pytest.UsageError(f"{path.name} must define a non-empty tool and object body")
        cases.append(pytest.param(tool, body, id=path.stem))
    if not cases:
        raise pytest.UsageError("At least one read-only tool case is required")
    return cases


@pytest.mark.live
def test_real_mcp_exposes_every_configured_tool(live_mcp_context):
    async def run():
        settings, _ = await live_mcp_context()
        client = StreamableHTTPMCPClient(settings)
        try:
            return await client.list_tools()
        finally:
            await client.aclose()

    exposed = {tool.get("name") for tool in asyncio.run(run())}
    expected = {case.values[0] for case in _tool_cases()}
    assert expected <= exposed


@pytest.mark.live
@pytest.mark.parametrize("tool,body", _tool_cases())
def test_real_read_only_tool(tool: str, body: dict[str, Any], live_mcp_context):
    async def run():
        settings, _ = await live_mcp_context()
        client = StreamableHTTPMCPClient(settings)
        try:
            return await client.call_tool(tool, body)
        finally:
            await client.aclose()

    result = asyncio.run(run())
    assert result is not None
