from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.contracts import RecipeProvider
from app.core.dependencies import get_recipe_provider
from app.models.recipe import Recipe

router = APIRouter(prefix="/recipes", tags=["recipes"])


@router.get("/search", response_model=list[Recipe])
async def search_recipes(q: Annotated[str, Query(min_length=1)], provider: Annotated[RecipeProvider, Depends(get_recipe_provider)]) -> list[Recipe]:
    return await provider.search(q)


@router.get("/{recipe_id}", response_model=Recipe)
async def get_recipe(recipe_id: str, provider: Annotated[RecipeProvider, Depends(get_recipe_provider)]) -> Recipe:
    recipe = await provider.get_by_id(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe
