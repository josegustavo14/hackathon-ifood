from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.core.contracts import NutritionProvider, RecipeProvider
from app.core.dependencies import get_nutrition_provider, get_recipe_provider
from app.models.common import Contract
from app.models.nutrition import NutritionCalculation
from app.nutrition.usda import USDAUpstreamError

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


class NutritionCalculateRequest(Contract):
    recipe_id: str
    servings: int = Field(gt=0)
    include_optional: bool = False


@router.post("/calculate", response_model=NutritionCalculation)
async def calculate_nutrition(
    request: NutritionCalculateRequest,
    provider: Annotated[NutritionProvider, Depends(get_nutrition_provider)],
    recipes: Annotated[RecipeProvider, Depends(get_recipe_provider)],
) -> NutritionCalculation:
    recipe = await recipes.get_by_id(request.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    try:
        return await provider.calculate(recipe, request.servings, request.include_optional)
    except USDAUpstreamError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
