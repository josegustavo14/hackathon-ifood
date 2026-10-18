"""Small Streamable-HTTP MCP client used by the iFood gateway.

It uses JSON-RPC directly instead of tying the API service to a particular MCP
SDK version.  MCP servers can answer either with JSON or an SSE event stream.
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import httpx

from .settings import IFoodMCPSettings


class MCPError(RuntimeError):
    pass


class MCPProtocolError(MCPError):
    pass


class MCPAuthenticationError(MCPError):
    """The consumer MCP rejected or could not identify the OAuth token."""


class MCPAuthorizationError(MCPError):
    """The authenticated OAuth token cannot invoke the requested tool."""


class MCPToolError(MCPError):
    """Structured domain error returned inside a successful MCP response."""

    def __init__(self, code: str, message: str, payload: Mapping[str, Any]) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.payload = payload
        raw_error = payload.get("error", payload.get("errors", {}))
        error = raw_error if isinstance(raw_error, Mapping) else {}
        self.details = error.get("details", {}) if isinstance(error.get("details", {}), Mapping) else {}
        self.user_friendly_message = (
            str(error["userFriendlyMessage"])
            if error.get("userFriendlyMessage")
            else message
        )
        actions = error.get("suggestedActions", [])
        self.suggested_actions = tuple(actions) if isinstance(actions, list) else ()


class BearerTokenProvider:
    """Supplies only an already-issued user token.

    iFood's documented flow is Authorization Code with PKCE. Token acquisition
    belongs to ``auth.exchange_authorization_code``; this transport must never
    silently substitute an undocumented client-credentials grant.
    """
    def __init__(self, settings: IFoodMCPSettings) -> None:
        self._access_token = settings.access_token

    async def authorization_header(self) -> str | None:
        return f"Bearer {self._access_token}" if self._access_token else None


class StreamableHTTPMCPClient:
    def __init__(self, settings: IFoodMCPSettings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.timeout_seconds, transport=transport)
        self._auth = BearerTokenProvider(settings)
        self._session_id: str | None = None
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        await self._ensure_initialized()
        result = await self._request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, Mapping):
            raise MCPProtocolError("tools/call returned an invalid result")
        payload = self._tool_payload(result)
        if result.get("isError"):
            if isinstance(payload, Mapping):
                raw_error = payload.get("error", payload.get("errors"))
                if isinstance(raw_error, Mapping):
                    code = str(raw_error.get("code", "IFOOD_MCP_ERROR"))
                    message = str(raw_error.get("message", "iFood MCP operation failed"))
                    raise MCPToolError(code, message, payload)
            raise MCPError(self._content_message(result) or f"iFood MCP tool {name} failed")
        return payload

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        result = await self._request("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, Mapping) else []
        if not isinstance(tools, list):
            raise MCPProtocolError("tools/list returned an invalid tools field")
        return [tool for tool in tools if isinstance(tool, dict)]

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            result = await self._request("initialize", {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "ifood-chef-ai", "version": "0.1.0"},
            })
            if not isinstance(result, Mapping):
                raise MCPProtocolError("MCP initialize returned an invalid result")
            await self._notification("notifications/initialized", {})
            self._initialized = True

    async def _notification(self, method: str, params: dict[str, Any]) -> None:
        await self._post({"jsonrpc": "2.0", "method": method, "params": params}, expects_response=False)

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = str(uuid4())
        payload = await self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, expects_response=True)
        if not isinstance(payload, Mapping):
            raise MCPProtocolError("MCP response was not a JSON object")
        if "error" in payload:
            error = payload["error"]
            message = error.get("message", "unknown MCP error") if isinstance(error, Mapping) else str(error)
            raise MCPError(f"iFood MCP error: {message}")
        if payload.get("id") != request_id or "result" not in payload:
            raise MCPProtocolError("MCP response did not match the JSON-RPC request")
        return payload["result"]

    async def _post(self, body: dict[str, Any], *, expects_response: bool) -> Any:
        authorization = await self._auth.authorization_header()
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if authorization:
            headers["Authorization"] = authorization
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        response = await self._client.post(self._settings.mcp_url, json=body, headers=headers)
        if session_id := response.headers.get("Mcp-Session-Id"):
            self._session_id = session_id
        if response.status_code == 401:
            raise MCPAuthenticationError("iFood MCP requires a valid access token")
        if response.status_code == 403:
            raise MCPAuthorizationError("iFood MCP denied this operation for the current OAuth token")
        if response.is_error:
            raise MCPError(f"iFood MCP returned HTTP {response.status_code}")
        if not expects_response:
            return None
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            try:
                return response.json()
            except json.JSONDecodeError as exc:
                raise MCPProtocolError("MCP returned invalid JSON") from exc
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError as exc:
                    raise MCPProtocolError("MCP returned invalid SSE JSON") from exc
        raise MCPProtocolError("MCP SSE response had no data event")

    @staticmethod
    def _content_message(result: Mapping[str, Any]) -> str | None:
        for part in result.get("content", []):
            if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                return part["text"]
        return None

    @classmethod
    def _tool_payload(cls, result: Mapping[str, Any]) -> Any:
        if "structuredContent" in result:
            return result["structuredContent"]
        text = cls._content_message(result)
        if text is None:
            return result
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
