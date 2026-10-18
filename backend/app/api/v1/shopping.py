from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator

from app.core.contracts import IFoodGateway, RecipeProvider, ShoppingEngine
from app.core.dependencies import get_ifood_gateway, get_recipe_provider, get_shopping_engine
from app.integrations.ifood.mcp import MCPAuthenticationError, MCPAuthorizationError, MCPError
from app.models.common import Contract
from app.models.shopping import ShoppingList

router = APIRouter(prefix="/shopping", tags=["shopping"])


class ShoppingCalculateRequest(Contract):
    recipe_id: str
    servings: int = Field(gt=0)


class ShoppingMatchRequest(Contract):
    shopping_list: ShoppingList
    merchant_id: str | None = None
    address_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


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
        try:
            products = await gateway.search_products(
                item.ingredient.name, request.merchant_id,
                address_id=request.address_id,
                latitude=request.latitude,
                longitude=request.longitude,
            )
        except MCPAuthenticationError as exc:
            raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
        except MCPAuthorizationError as exc:
            raise HTTPException(status_code=403, detail="iFood denied search for the current OAuth token") from exc
        except MCPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        for product in products:
            candidates[product.id] = product
    return engine.match_products(request.shopping_list, list(candidates.values()))
