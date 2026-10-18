from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
from fastapi import HTTPException, Request

from app.core.config import get_settings
from app.core.contracts import IFoodGateway, NutritionProvider, RecipeProvider, ShoppingEngine
from app.integrations.ifood import IFoodMCPGateway, IFoodShoppingEngine
from app.integrations.ifood.auth import OAUTH_SESSION_COOKIE, OAuthTokenError, oauth_token_store, refresh_access_token
from app.integrations.ifood.settings import IFoodConfigurationError, IFoodMCPSettings
from app.mocks.services import MockIFoodGateway, MockNutritionProvider, MockRecipeProvider, MockShoppingEngine
from app.nutrition.usda import USDAClient, USDANutritionProvider


def require_mock_mode() -> None:
    if not get_settings().mock_mode:
        raise HTTPException(status_code=503, detail="Real integrations are not configured in EP00")


def get_recipe_provider() -> RecipeProvider:
    require_mock_mode()
    return MockRecipeProvider()


async def get_ifood_gateway(request: Request) -> AsyncIterator[IFoodGateway]:
    if get_settings().mock_mode:
        yield MockIFoodGateway()
        return
    try:
        session_id = request.cookies.get(OAUTH_SESSION_COOKIE)
        tokens = oauth_token_store.get(session_id) if session_id else None
        if not session_id or not tokens:
            raise HTTPException(status_code=401, detail="Connect your iFood account first")
        if oauth_token_store.refresh_required(session_id):
            async with oauth_token_store.refresh_lock(session_id):
                tokens = oauth_token_store.get(session_id)
                if tokens and oauth_token_store.refresh_required(session_id):
                    if not tokens.refresh_token:
                        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account")
                    refreshed = await refresh_access_token(IFoodMCPSettings.from_environment(), tokens.refresh_token)
                    tokens = replace(refreshed, granted_scopes=refreshed.granted_scopes or tokens.granted_scopes)
                    oauth_token_store.put(session_id, tokens)
        if not tokens:
            raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account")
        gateway = IFoodMCPGateway.from_environment(tokens.access_token)
        try:
            yield gateway
        finally:
            await gateway.aclose()
    except IFoodConfigurationError as exc:
        raise HTTPException(status_code=503, detail="Real iFood MCP integration is not configured") from exc
    except OAuthTokenError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc


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
    if get_settings().mock_mode:
        return MockShoppingEngine()
    return IFoodShoppingEngine()
