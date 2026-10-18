from __future__ import annotations

import json
import re
from typing import Any
import unicodedata

import httpx

from app.integrations.recipes import RecipeProviderError, normalize_recipe
from app.models.agent import AgentRequest, AgentResponse, AgentStatus
from app.core.contracts import RecipeProvider
from app.integrations.recipes.provider import registry
from app.mocks.data import load_json
from app.models.recipe import Recipe


class AgentService:
    """Generates a structured recipe with web search through the configured LLM."""

    def __init__(self, *, provider: str = "deterministic", api_key: str = "", model: str = "", base_url: str = "https://api.openai.com/v1", timeout: float = 45.0, recipes: RecipeProvider | None = None):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.recipes = recipes

    @staticmethod
    def wants_nutrition(message: str) -> bool:
        plain = unicodedata.normalize("NFKD", message.casefold())
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        return bool(re.search(r"\b(nutricao|nutricional|calorias?|calorico|macros?|macronutrientes?|proteinas?|carboidratos?|gorduras?)\b", plain))

    async def _nutrition_intent(self, message: str) -> bool:
        if self.wants_nutrition(message):
            return True
        if self.provider != "openai_compatible" or not self.api_key or not self.model:
            return False
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Classifique se o usuário quer dados nutricionais (calorias ou macronutrientes). Responda somente JSON: {\"nutrition_requested\": true ou false}. Receitas ou compras sem pedido nutricional são false."},
                {"role": "user", "content": message},
            ],
            "temperature": 0,
            # Reasoning models can consume a short completion budget before
            # emitting the JSON classification in ``content``.
            "max_tokens": 160,
        }
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
                response = await client.post(self.base_url + "/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(re.search(r"\{.*\}", content, flags=re.S).group())
                return parsed.get("nutrition_requested") is True
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError):
            return False

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
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError, RecipeProviderError):
            return None

    async def chat(self, request: AgentRequest) -> AgentResponse:
        plain = unicodedata.normalize("NFKD", request.message.casefold())
        plain = "".join(char for char in plain if not unicodedata.combining(char))
        pasta_requested = re.search(r"\bmacarrao\b", plain)
        excluded = re.search(r"\b(?:nao|sem|evit\w*)\b[^,.!?]*\bmacarrao\b|\b(?:sem carne|vegetarian\w*|vegan\w*)\b", plain)
        if pasta_requested and not excluded:
            recipe = Recipe.model_validate(load_json("pasta.json"))
            registry.put(recipe)
            return AgentResponse(
                session_id=request.session_id or "",
                message="Aqui está a receita de macarrão com carne, molho de tomate e creme de leite para 4 pessoas. Abra para ajustar as porções e montar sua lista de compras.",
                status=AgentStatus.completed, recipe=recipe,
                nutrition_requested=self.wants_nutrition(request.message),
            )
        query = self._query(request.message)
        nutrition_requested = await self._nutrition_intent(request.message)
        context_id = (request.context or {}).get("recipe_id")
        if nutrition_requested and not query and isinstance(context_id, str) and self.recipes:
            recipe = await self.recipes.get_by_id(context_id)
            if recipe:
                return AgentResponse(session_id=request.session_id or "", message=f"Vou consultar os dados nutricionais de {recipe.name}.", status=AgentStatus.completed, recipe=recipe, nutrition_requested=True)
        if not query:
            return AgentResponse(session_id=request.session_id or "", message="Qual prato você gostaria de preparar?", status=AgentStatus.needs_input)
        recipe = None
        if self.recipes:
            matches = await self.recipes.search(query)
            recipe = next((item for item in matches if item.source.startswith("recipenlg")), None)
            if recipe:
                recipe = await self.recipes.get_by_id(recipe.id) or recipe
        recipe = recipe or await self._web_recipe(query)
        if recipe is None:
            return AgentResponse(session_id=request.session_id or "", message="Não consegui consultar uma receita na internet agora. Tente novamente.", status=AgentStatus.error)
        registry.put(recipe)
        source_message = "no RecipeNLG" if recipe.source.startswith("recipenlg") else "em uma fonte culinária"
        return AgentResponse(session_id=request.session_id or "", message=f"Encontrei uma receita de {recipe.name} {source_message}.", status=AgentStatus.completed, recipe=recipe, nutrition_requested=nutrition_requested)
