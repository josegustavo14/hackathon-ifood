"""Shared recipe lookup for HTTP endpoints and the agent."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from app.integrations.recipes.recipenlg import RecipeNLGProvider
from app.mocks.services import MockRecipeProvider
from app.models.recipe import Recipe


class RecipeRegistry:
    """Bounded process-local registry for LLM recipes used by follow-up requests."""

    def __init__(self, capacity: int = 256):
        self.capacity = capacity
        self._recipes: OrderedDict[str, Recipe] = OrderedDict()

    def put(self, recipe: Recipe) -> None:
        self._recipes[recipe.id] = recipe
        self._recipes.move_to_end(recipe.id)
        while len(self._recipes) > self.capacity:
            self._recipes.popitem(last=False)

    def get(self, recipe_id: str) -> Recipe | None:
        return self._recipes.get(recipe_id)


registry = RecipeRegistry()


class CombinedRecipeProvider:
    def __init__(self, index_path: Path | None = None):
        self.dataset = RecipeNLGProvider(index_path) if index_path else None
        self.mock = MockRecipeProvider()

    async def search(self, query: str) -> list[Recipe]:
        if self.dataset:
            found = await self.dataset.search(query)
            if found:
                return found
        return await self.mock.search(query)

    async def get_by_id(self, recipe_id: str) -> Recipe | None:
        if recipe := registry.get(recipe_id):
            return recipe
        if self.dataset and (recipe := await self.dataset.get_by_id(recipe_id)):
            return recipe
        return await self.mock.get_by_id(recipe_id)
