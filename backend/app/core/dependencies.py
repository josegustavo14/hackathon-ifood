from fastapi import HTTPException

from app.core.config import get_settings
from app.core.contracts import IFoodGateway, NutritionProvider, RecipeProvider, ShoppingEngine
from app.mocks.services import MockIFoodGateway, MockNutritionProvider, MockRecipeProvider, MockShoppingEngine


def require_mock_mode() -> None:
    if not get_settings().mock_mode:
        raise HTTPException(status_code=503, detail="Real integrations are not configured in EP00")


def get_recipe_provider() -> RecipeProvider:
    require_mock_mode()
    return MockRecipeProvider()


def get_ifood_gateway() -> IFoodGateway:
    require_mock_mode()
    return MockIFoodGateway()


def get_nutrition_provider() -> NutritionProvider:
    require_mock_mode()
    return MockNutritionProvider()


def get_shopping_engine() -> ShoppingEngine:
    require_mock_mode()
    return MockShoppingEngine()
