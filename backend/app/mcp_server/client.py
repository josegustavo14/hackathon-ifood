"""Bounded HTTP bridge; the REST backend remains the source of truth."""

from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import TypeAdapter, ValidationError


class ChefAPI:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        url = urlsplit(base_url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("CHEF_API_URL deve ser uma origem HTTP(S), sem credenciais ou caminho. Exemplo: http://127.0.0.1:8000")
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    async def request(self, method: str, path: str, response_type: Any, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=30, transport=self.transport,
                follow_redirects=False, trust_env=False,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise ToolError("A API Chef AI excedeu o limite de 30 segundos. Tente novamente.") from error
        except httpx.RequestError as error:
            raise ToolError("Não foi possível conectar à API Chef AI. Inicie o FastAPI e confira CHEF_API_URL.") from error

        if not response.is_success:
            try:
                data = response.json()
                envelope = data.get("error", {}) if isinstance(data, dict) else {}
                message = envelope.get("message", "Falha na API Chef AI")
            except (ValueError, AttributeError):
                message = "Falha na API Chef AI"
            raise ToolError(f"API Chef AI HTTP {response.status_code}: {str(message)[:500]}")
        try:
            return TypeAdapter(response_type).validate_python(response.json())
        except (ValueError, ValidationError) as error:
            raise ToolError("A API retornou dados incompatíveis com o contrato Chef AI.") from error
