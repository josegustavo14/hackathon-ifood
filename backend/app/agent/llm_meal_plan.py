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


# A weekly plan with 28 meals serializes to several thousand tokens. Providers that cap
# completions at their default truncate the JSON, which then fails to parse.
MAX_COMPLETION_TOKENS = 8000


def _reason(exc: Exception) -> str:
    """Describe the failure without leaking credentials from the request."""
    cause = exc.__cause__ or exc
    response = getattr(cause, "response", None)
    detail = f"{cause} {response.text}" if response is not None else str(cause)
    detail = re.sub(r"(Bearer|api[_-]?key)\s*\S+", r"\1 ***", detail, flags=re.I)
    return f"{type(cause).__name__}: {detail[:160]}" if detail else type(cause).__name__


def _plan_id(filename: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", filename.casefold()).strip("-") or "upload"
    return f"meal-plan-{slug}"


def _from_payload(payload: dict, source_filename: str) -> MealPlan:
    payload = dict(payload)
    payload["id"] = _plan_id(source_filename)
    payload["source_filename"] = source_filename
    payload.setdefault("extraction_warnings", [])
    return MealPlan.model_validate(payload)


SYSTEM_PROMPT = r'''
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

ANTES DE EXTRAIR, RECONSTITUA O TEXTO:
O texto vem de uma extração de PDF e as linhas chegam quebradas no meio das frases.
Primeiro junte as linhas partidas, depois interprete o resultado.
A. Uma linha que não começa com dia, refeição, "Alternativas" ou marcador de lista é a
   continuação da linha anterior. Junte as duas com um espaço antes de interpretar.
B. São sinais claros de quebra: a linha anterior termina em número ("... lombo suíno; 150"),
   em unidade, em ";", em "," ou em "de"; ou a linha atual começa por unidade
   ("g farofa de couve"), por ";" ou por minúscula.
C. Depois de juntar, "...; 150" + "g farofa de couve" é UM ingrediente:
   150 g de farofa de couve. Nunca gere o ingrediente "150" nem "g farofa de couve".
D. Palavras soltas numa linha ("banana", "cenoura", "sem açúcar") são o final do
   ingrediente anterior, não um ingrediente novo sem quantidade.
E. Nunca registre em extraction_warnings uma quebra de linha que você mesmo reconstituiu.
   Os avisos são para ambiguidade real do plano, não para ruído da extração.

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
    validação. Não transforme essas linhas em refeições ou ingredientes. Isso inclui
    linhas de identificação e de meta do plano, como "PLANO ALIMENTAR SEMANAL",
    "Paciente: Maria Silva", "1800 kcal/dia", "Nutricionista: ... CRN 12345" e datas.
    Descarte-as em silêncio: não são refeição, ingrediente nem aviso.
11. Não invente dias, refeições, ingredientes, quantidades ou frequência. Quando a
    frequência não estiver escrita, use 1 para aquela ocorrência.
12. Gere ids simples em minúsculas, sem acentos e com hífens.
13. O nome do ingrediente é só o alimento. Remova restos de formatação: unidade órfã no
    início ("g salada de folhas" vira "salada de folhas"), números soltos, ":", "|",
    marcadores e "de/do/da" no começo. Nunca crie um ingrediente cujo nome seja um
    número, uma unidade ou um trecho de outra linha.

EXEMPLOS:

Entrada (linha quebrada pela extração do PDF):
"Almoço: 150 g arroz integral; 100 g feijão preto; 180 g lombo suíno; 150
g farofa de couve"
Saída parcial: {
  "name": "Almoço",
  "ingredients": [
    {"id": "arroz-integral", "name": "arroz integral", "quantity": 150, "unit": "g", "optional": false, "notes": null},
    {"id": "feijao-preto", "name": "feijão preto", "quantity": 100, "unit": "g", "optional": false, "notes": null},
    {"id": "lombo-suino", "name": "lombo suíno", "quantity": 180, "unit": "g", "optional": false, "notes": null},
    {"id": "farofa-de-couve", "name": "farofa de couve", "quantity": 150, "unit": "g", "optional": false, "notes": null}
  ],
  "alternative_groups": [],
  "extraction_warnings": []
}

Entrada (cabeçalho do documento):
"PLANO ALIMENTAR SEMANAL
Paciente: Julia Carvalho - 1800 kcal/dia"
Saída parcial: {"days": [], "meals": [], "extraction_warnings": []}

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


class DeterministicMealPlanInterpreter:
    async def interpret(self, text: str, source_filename: str) -> MealPlan:
        return parse(text, source_filename)


class OpenAICompatibleMealPlanInterpreter:
    """Interpret extracted PDF text through an OpenAI-compatible JSON endpoint."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 45.0, reasoning_effort: str = ""):
        self.api_key = api_key
        self.model = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort

    async def interpret(self, text: str, source_filename: str) -> MealPlan:
        system = SYSTEM_PROMPT
        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": MAX_COMPLETION_TOKENS,
            "response_format": {"type": "json_object"},
            # Reasoning models spend the completion budget before answering and return an
            # empty body, which the provider rejects as invalid JSON. Keep the effort low.
            **({"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}),
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


async def interpret_meal_plan(text: str, source_filename: str, *, provider: str, api_key: str, model: str, base_url: str, timeout: float, reasoning_effort: str = "") -> MealPlan:
    if provider == "openai_compatible" and api_key and model:
        try:
            interpreter = OpenAICompatibleMealPlanInterpreter(api_key, model, base_url, timeout, reasoning_effort)
            return await interpreter.interpret(text, source_filename)
        except LLMInterpretationError as exc:
            fallback = await DeterministicMealPlanInterpreter().interpret(text, source_filename)
            fallback.extraction_warnings.append(f"A interpretação por LLM falhou ({_reason(exc)}); foi usado o parser determinístico.")
            return fallback
    return await DeterministicMealPlanInterpreter().interpret(text, source_filename)
