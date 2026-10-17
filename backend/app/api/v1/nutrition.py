from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.core.contracts import NutritionProvider
from app.core.dependencies import get_nutrition_provider
from app.models.common import Contract
from app.models.nutrition import NutritionFacts

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


class NutritionCalculateRequest(Contract):
    recipe_id: str
    servings: int = Field(gt=0)


@router.post("/calculate", response_model=NutritionFacts)
async def calculate_nutrition(request: NutritionCalculateRequest, provider: Annotated[NutritionProvider, Depends(get_nutrition_provider)]) -> NutritionFacts:
    nutrition = await provider.get_nutrition(request.recipe_id, request.servings)
    if nutrition is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return nutrition
