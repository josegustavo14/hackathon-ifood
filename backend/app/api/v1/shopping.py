import asyncio
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator

from app.core.contracts import IFoodGateway, RecipeProvider, ShoppingEngine
from app.core.config import get_settings
from app.core.dependencies import get_ifood_gateway, get_recipe_provider, get_shopping_engine
from app.integrations.ifood.mcp import MCPAuthenticationError, MCPAuthorizationError, MCPError
from app.integrations.ifood.models import AvailabilityStatus
from app.models.common import Contract
from app.models.shopping import ShoppingItemStatus, ShoppingList, ShoppingListStatus
from app.shopping.catalog import catalog_search_terms
from app.shopping.engine import DeterministicShoppingEngine
from app.shopping.models import ShoppingPlan, ShoppingPlanRequest

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


class ShoppingSelectProductRequest(Contract):
    shopping_list: ShoppingList
    ingredient_id: str
    product_id: str
    purchase_quantity: int = Field(ge=1, le=99)
    address_id: str | None = None


@router.post("/plan", response_model=ShoppingPlan)
async def plan_shopping(request: ShoppingPlanRequest) -> ShoppingPlan:
    """Optimize structured recipes against supplied catalog data without MCP calls."""
    try:
        return DeterministicShoppingEngine().plan(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/calculate", response_model=ShoppingList)
async def calculate_shopping(request: ShoppingCalculateRequest, recipes: Annotated[RecipeProvider, Depends(get_recipe_provider)], engine: Annotated[ShoppingEngine, Depends(get_shopping_engine)]) -> ShoppingList:
    recipe = await recipes.get_by_id(request.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return engine.calculate(recipe, request.servings)


@router.post("/match", response_model=ShoppingList)
async def match_shopping(request: ShoppingMatchRequest, gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)], engine: Annotated[ShoppingEngine, Depends(get_shopping_engine)]) -> ShoppingList:
    candidates = {}
    try:
        latitude, longitude = request.latitude, request.longitude
        if request.address_id:
            addresses = await gateway.list_addresses()
            selected = next((address for address in addresses.addresses if address.address_id == request.address_id), None)
            if selected is None or selected.coordinates is None:
                raise ValueError("The selected iFood address is unavailable or has no coordinates")
            latitude, longitude = selected.coordinates.latitude, selected.coordinates.longitude
        limit = asyncio.Semaphore(3)

        async def search(name: str):
            async with limit:
                return await gateway.search_products(
                    name, request.merchant_id,
                    address_id=request.address_id, latitude=latitude, longitude=longitude,
                )

        names = list(dict.fromkeys(term for item in request.shopping_list.items
                                   for term in catalog_search_terms(item.ingredient.name)))
        results = await asyncio.wait_for(asyncio.gather(*(search(name) for name in names)), timeout=75)
        for products in results:
            for product in products:
                candidates[product.id] = product
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied search for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail="iFood product search is temporarily unavailable; retry later") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="iFood product search timed out; no cart was changed") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return engine.match_products(request.shopping_list, list(candidates.values()))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/select-product", response_model=ShoppingList)
async def select_product(request: ShoppingSelectProductRequest,
                         gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)]) -> ShoppingList:
    """Apply an explicit package count to a product suggested by the catalog."""
    index = next((index for index, item in enumerate(request.shopping_list.items)
                  if item.ingredient.id == request.ingredient_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Ingredient not found in shopping list")
    item = request.shopping_list.items[index]
    if item.status not in {ShoppingItemStatus.needs_review, ShoppingItemStatus.unavailable}:
        raise HTTPException(status_code=409, detail="Ingredient is not awaiting a manual product choice")
    product = next((product for product in item.suggested_products if product.id == request.product_id), None)
    if product is None or not product.available:
        raise HTTPException(status_code=409, detail="Choose an available product suggested for this ingredient")
    merchants = {other.selected_product.merchant_id for offset, other in enumerate(request.shopping_list.items)
                 if offset != index and other.selected_product is not None}
    if merchants and merchants != {product.merchant_id}:
        raise HTTPException(status_code=409, detail="All cart products must come from the same merchant")
    if not get_settings().mock_mode:
        if not request.address_id:
            raise HTTPException(status_code=422, detail="A saved delivery address is required")
        if product.source != "ifood_mcp":
            raise HTTPException(status_code=409, detail="Manual selection requires a real iFood product")
        try:
            current = await gateway.get_item(product.id, product.merchant_id, address_id=request.address_id)
        except MCPAuthenticationError as exc:
            raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
        except MCPAuthorizationError as exc:
            raise HTTPException(status_code=403, detail="iFood denied product details for this OAuth token") from exc
        except MCPError as exc:
            raise HTTPException(status_code=502, detail="iFood product details are temporarily unavailable") from exc
        if current.availability != AvailabilityStatus.available or current.price != product.price:
            raise HTTPException(status_code=409, detail="Product price or availability changed; search again")
    items = list(request.shopping_list.items)
    items[index] = item.model_copy(update={
        "selected_product": product, "suggested_products": [],
        "purchase_quantity": request.purchase_quantity,
        "total_price": product.price * request.purchase_quantity,
        "status": ShoppingItemStatus.matched, "reason": "manually_selected_unverified_quantity",
    })
    unresolved = [line.ingredient for line in items if line.status != ShoppingItemStatus.matched]
    subtotal = sum((line.total_price for line in items), Decimal("0.00"))
    return request.shopping_list.model_copy(update={
        "items": items, "unresolved_ingredients": unresolved, "estimated_subtotal": subtotal,
        "status": ShoppingListStatus.needs_review if unresolved else ShoppingListStatus.ready_for_review,
    })
