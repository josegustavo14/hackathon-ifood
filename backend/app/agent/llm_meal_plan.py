from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from app.models.recipe import MealPlan
from .meal_plan_extractor import MealPlanParseError, parse


class MealPlanInterpreter(Protocol):
    async def interpret(self, text: str, source_filename: str) -> MealPlan: ...


class LLMInterpretationError(ValueError):
    """The model response was unavailable or did not match the contract."""


def _plan_id(filename: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", filename.casefold()).strip("-") or "upload"
    return f"meal-plan-{slug}"


def _from_payload(payload: dict, source_filename: str) -> MealPlan:
    payload = dict(payload)
    payload["id"] = _plan_id(source_filename)
    payload["source_filename"] = source_filename
    payload.setdefault("extraction_warnings", [])
    return MealPlan.model_validate(payload)


class DeterministicMealPlanInterpreter:
    async def interpret(self, text: str, source_filename: str) -> MealPlan:
        return parse(text, source_filename)


class OpenAICompatibleMealPlanInterpreter:
    """Interpret extracted PDF text through an OpenAI-compatible JSON endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 45.0):
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout

    async def interpret(self, text: str, source_filename: str) -> MealPlan:
        system = r'''
Você é um especialista em extração estruturada de planos alimentares em português.
Sua tarefa é converter TEXTO EXTRAÍDO de um PDF em um único objeto JSON válido.
Responda SOMENTE com JSON, sem markdown, comentários ou explicações.

FORMATO OBRIGATÓRIO:
{
  "days": ["Segunda"],
  "meals": [
    {
      "day": "Segunda",
      "name": "Almoço",
      "frequency_per_week": 1,
      "ingredients": [
        {"id": "arroz", "name": "arroz", "quantity": 100, "unit": "g", "optional": false, "notes": null}
      ],
      "alternative_groups": []
    }
  ],
  "extraction_warnings": []
}

REGRAS DE INTERPRETAÇÃO:
1. Identifique dias mesmo em formatos como "SEGUNDA-FEIRA", "2ª feira" ou "Dia 2 - terça".
2. Reconheça nomes equivalentes de refeições: café da manhã, desjejum, brunch, colação,
   lanche da manhã, almoço, lanche da tarde, jantar e ceia.
3. Extraia ingredientes mesmo quando aparecem dentro de uma frase:
   "Sopa com 150 g de batata e 100 g de frango" vira dois ingredientes.
4. Aceite quantidades decimais e frações. Para "1/2 xícara de aveia", use quantity 0.5,
   unit "unit" e notes "medida caseira original: xícara". Nunca converta xícara para gramas.
5. Use somente estas unidades: "g", "kg", "ml", "l" ou "unit".
6. Para unidades como ovos, fatias, colheres, xícaras e unidades, use unit "unit" e
   preserve a medida original ou o contexto em notes quando isso for relevante.
7. Para "a gosto", "quanto baste", "QB" ou quantidade ausente, NÃO invente quantidade.
   Não crie ingrediente sem quantidade; registre um aviso em extraction_warnings.
8. Separe alternativas indicadas por "ou", "alternativa", "opção" ou "escolher".
   Nunca some alternativas aos ingredientes principais.
9. "2 ovos cozidos" significa um ingrediente chamado "ovos cozidos", quantity 2,
   unit "unit"; não remova a palavra ovos do nome.
10. Ignore títulos do documento, cabeçalhos de tabela, rodapés, páginas e instruções de
    validação. Não transforme essas linhas em refeições ou ingredientes.
11. Não invente dias, refeições, ingredientes, quantidades ou frequência. Quando a
    frequência não estiver escrita, use 1 para aquela ocorrência.
12. Gere ids simples em minúsculas, sem acentos e com hífens.

EXEMPLOS:

Entrada: "Almoço: Sopa com 150 g de batata e 100 g de frango"
Saída parcial: {
  "name": "Almoço",
  "ingredients": [
    {"id": "batata", "name": "batata", "quantity": 150, "unit": "g", "optional": false, "notes": null},
    {"id": "frango", "name": "frango", "quantity": 100, "unit": "g", "optional": false, "notes": null}
  ], "alternative_groups": []
}

Entrada: "Alternativas: 2 ovos cozidos ou 120 g peixe"
Saída parcial: {
  "ingredients": [],
  "alternative_groups": [{"choose": 1, "options": [
    {"name": "ovos cozidos", "ingredients": [{"id": "ovos-cozidos", "name": "ovos cozidos", "quantity": 2, "unit": "unit", "optional": false, "notes": null}]},
    {"name": "peixe", "ingredients": [{"id": "peixe", "name": "peixe", "quantity": 120, "unit": "g", "optional": false, "notes": null}]}
  ]}
}

Entrada: "1/2 xícara de aveia; sal a gosto"
Saída parcial: {
  "ingredients": [
    {"id": "aveia", "name": "aveia", "quantity": 0.5, "unit": "unit", "optional": false, "notes": "medida caseira original: xícara"}
  ],
  "extraction_warnings": ["A quantidade do sal não foi especificada."]
}
'''
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Arquivo: {source_filename}\n\nTexto extraído:\n{text}"},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"}, json=body)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return _from_payload(json.loads(content), source_filename)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise LLMInterpretationError("The meal-plan LLM response could not be validated") from exc


async def interpret_meal_plan(text: str, source_filename: str, *, provider: str, api_key: str, model: str, base_url: str, timeout: float) -> MealPlan:
    if provider == "openai_compatible" and api_key and model:
        try:
            return await OpenAICompatibleMealPlanInterpreter(api_key, model, base_url, timeout).interpret(text, source_filename)
        except LLMInterpretationError:
            fallback = await DeterministicMealPlanInterpreter().interpret(text, source_filename)
            fallback.extraction_warnings.append("A interpretação por LLM falhou; foi usado o parser determinístico.")
            return fallback
    return await DeterministicMealPlanInterpreter().interpret(text, source_filename)
