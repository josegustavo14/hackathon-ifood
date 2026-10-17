from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from app.core.contracts import IFoodGateway, RecipeProvider, ShoppingEngine
from app.core.dependencies import get_ifood_gateway, get_recipe_provider, get_shopping_engine
from app.models.common import Contract
from app.models.shopping import ShoppingList

router = APIRouter(prefix="/shopping", tags=["shopping"])


class ShoppingCalculateRequest(Contract):
    recipe_id: str
    servings: int = Field(gt=0)


class ShoppingMatchRequest(Contract):
    shopping_list: ShoppingList
    merchant_id: str | None = None


@router.post("/calculate", response_model=ShoppingList)
async def calculate_shopping(request: ShoppingCalculateRequest, recipes: Annotated[RecipeProvider, Depends(get_recipe_provider)], engine: Annotated[ShoppingEngine, Depends(get_shopping_engine)]) -> ShoppingList:
    recipe = await recipes.get_by_id(request.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return engine.calculate(recipe, request.servings)


@router.post("/match", response_model=ShoppingList)
async def match_shopping(request: ShoppingMatchRequest, gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)], engine: Annotated[ShoppingEngine, Depends(get_shopping_engine)]) -> ShoppingList:
    candidates = {}
    for item in request.shopping_list.items:
        for product in await gateway.search_products(item.ingredient.name, request.merchant_id):
            candidates[product.id] = product
    return engine.match_products(request.shopping_list, list(candidates.values()))
