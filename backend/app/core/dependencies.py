from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException

from app.core.config import get_settings
from app.core.contracts import IFoodGateway, NutritionProvider, RecipeProvider, ShoppingEngine
from app.mocks.services import MockIFoodGateway, MockNutritionProvider, MockRecipeProvider, MockShoppingEngine
from app.nutrition.usda import USDAClient, USDANutritionProvider


def require_mock_mode() -> None:
    if not get_settings().mock_mode:
        raise HTTPException(status_code=503, detail="Real integrations are not configured in EP00")


def get_recipe_provider() -> RecipeProvider:
    require_mock_mode()
    return MockRecipeProvider()


def get_ifood_gateway() -> IFoodGateway:
    require_mock_mode()
    return MockIFoodGateway()


async def get_nutrition_provider() -> AsyncIterator[NutritionProvider]:
    settings = get_settings()
    if settings.nutrition_provider == "mock":
        yield MockNutritionProvider()
        return
    if settings.nutrition_provider != "usda":
        raise HTTPException(status_code=503, detail="Unknown nutrition provider")
    if not settings.usda_api_key:
        raise HTTPException(status_code=503, detail="USDA_API_KEY is required for USDA nutrition")
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield USDANutritionProvider(USDAClient(settings.usda_api_key, client))


def get_shopping_engine() -> ShoppingEngine:
    require_mock_mode()
    return MockShoppingEngine()
