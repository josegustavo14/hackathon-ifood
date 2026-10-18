"""Translate RecipeNLG labels without changing quantities or instructions."""

from __future__ import annotations

import json
import re

import httpx

from app.models.recipe import Recipe


async def localize_recipe(recipe: Recipe, *, api_key: str, model: str, base_url: str, timeout: float) -> Recipe:
    if not api_key or not model:
        return recipe
    source = {"name": recipe.name, "ingredients": [{"id": item.id, "name": item.name} for item in recipe.ingredients]}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Traduza para português do Brasil somente o nome da receita e os nomes dos ingredientes. Responda JSON válido com name e ingredients [{id,name}] na mesma ordem. Preserve todos os IDs. Não adicione nem remova ingredientes. Não inclua quantidades, unidades ou instruções."},
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 2048,
    }
    try:
        async with httpx.AsyncClient(timeout=min(timeout, 20.0)) as client:
            response = await client.post(base_url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=body)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        translated = json.loads(re.search(r"\{.*\}", content, flags=re.S).group())
        labels = translated["ingredients"]
        if not isinstance(labels, list) or len(labels) != len(recipe.ingredients):
            return recipe
        if any(label.get("id") != item.id or not isinstance(label.get("name"), str) or not label["name"].strip()
               for label, item in zip(labels, recipe.ingredients)):
            return recipe
        title = translated.get("name")
        if not isinstance(title, str) or not title.strip():
            return recipe
        ingredients = [item.model_copy(update={"name": label["name"].strip()}) for item, label in zip(recipe.ingredients, labels)]
        return recipe.model_copy(update={
            "name": title.strip(), "ingredients": ingredients,
            "description": (recipe.description or "") + " Nomes traduzidos automaticamente; confira antes de comprar.",
        })
    except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError, json.JSONDecodeError):
        return recipe
