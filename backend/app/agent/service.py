from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.integrations.recipes import normalize_recipe
from app.models.agent import AgentRequest, AgentResponse, AgentStatus


class AgentService:
    """Generates a structured recipe with web search through the configured LLM."""

    def __init__(self, *, provider: str = "deterministic", api_key: str = "", model: str = "", base_url: str = "https://api.openai.com/v1", timeout: float = 45.0):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _query(message: str) -> str | None:
        text = re.sub(r"\s+", " ", message.casefold()).strip()
        match = re.search(r"(?:receita|fazer|preparar|cozinhar)\s+(?:de|do|da|para)?\s*([^,.!?]+)", text)
        if not match:
            match = re.search(r"(?:quero|gostaria de|preciso de)\s+(?:uma?|um)?\s*(?:receita de|prato de)?\s*([^,.!?]+)", text)
        if not match:
            return None
        query = re.sub(r"^(?:uma?|um|uns|umas)\s+", "", match.group(1))
        query = re.sub(r"\s+(?:para|pra)\s+[^,.!?]*\s+(?:pessoas?|porções?|porcoes?)\b.*$", "", query)
        return query.strip(" .,!?") or None

    @staticmethod
    def _json_from_response(payload: dict[str, Any]) -> dict[str, Any]:
        content = payload.get("output_text", "")
        if not content:
            for item in payload.get("output", []):
                for part in item.get("content", []):
                    if part.get("type") in {"output_text", "text"}:
                        content += part.get("text", "")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            raise ValueError("LLM did not return a JSON recipe")
        value = json.loads(match.group())
        if not isinstance(value, dict):
            raise ValueError("LLM recipe payload is not an object")
        return value

    async def _web_recipe(self, query: str):
        if self.provider != "openai_compatible" or not self.api_key or not self.model:
            return None
        prompt = (
            f'Encontre uma receita de "{query}" usando busca na internet. '
            "Use browser_search obrigatoriamente e priorize fontes culinárias confiáveis como "
            "TudoGostoso, Panelinha e Receitas.com. Não invente informações nem URLs. "
            "Responda somente com JSON válido neste formato: "
            '{"name":"...","description":"...","servings":4,"ingredients":'
            '[{"name":"...","quantity":1,"unit":"unit","notes":null}],'
            '"instructions":["..."],"source_url":"https://..."}. '
            "Use apenas as unidades g, kg, ml, l ou unit e não inclua ingrediente sem quantidade."
        )
        body = {
            "model": self.model,
            "input": prompt,
            "tool_choice": "auto",
            "tools": [{"type": "browser_search"}],
            "max_output_tokens": 4096,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url + "/responses", headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
                response.raise_for_status()
                payload = self._json_from_response(response.json())
                return normalize_recipe(payload, source_url=payload.get("source_url"), source="llm_web")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def chat(self, request: AgentRequest) -> AgentResponse:
        query = self._query(request.message)
        if not query:
            return AgentResponse(session_id=request.session_id or "", message="Qual prato você gostaria de preparar?", status=AgentStatus.needs_input)
        recipe = await self._web_recipe(query)
        if recipe is None:
            return AgentResponse(session_id=request.session_id or "", message="Não consegui consultar uma receita na internet agora. Tente novamente.", status=AgentStatus.error)
        return AgentResponse(session_id=request.session_id or "", message=f"Encontrei uma receita de {recipe.name} em uma fonte culinária confiável.", status=AgentStatus.completed, recipe=recipe)
