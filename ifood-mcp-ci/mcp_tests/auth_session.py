"""Resolve a valid user access token through the product's OAuth services."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Protocol

from app.integrations.ifood.auth import OAuthTokenError, OAuthTokens, refresh_access_token
from app.integrations.ifood.settings import IFoodMCPSettings


class OAuthSessionUnavailable(RuntimeError):
    """The test user has no reusable OAuth authorization."""


class TokenStore(Protocol):
    def get(self, browser_session_id: str) -> OAuthTokens | None: ...

    def put(self, browser_session_id: str, tokens: OAuthTokens) -> None: ...

    def refresh_required(self, browser_session_id: str, leeway_seconds: int = 300) -> bool: ...

    def refresh_lock(self, browser_session_id: str): ...


RefreshFunction = Callable[[IFoodMCPSettings, str], Awaitable[OAuthTokens]]


async def get_valid_access_token(
    session_id: str,
    store: TokenStore,
    settings: IFoodMCPSettings,
    *,
    refresh: RefreshFunction = refresh_access_token,
) -> str:
    """Load, refresh when needed, and persist the test user's OAuth token pair."""
    tokens = store.get(session_id)
    if tokens is None:
        raise OAuthSessionUnavailable("The iFood test user is not authorized")

    if store.refresh_required(session_id):
        async with store.refresh_lock(session_id):
            tokens = store.get(session_id)
            if tokens is None:
                raise OAuthSessionUnavailable("The iFood test user authorization disappeared")
            if store.refresh_required(session_id):
                if not tokens.refresh_token:
                    raise OAuthSessionUnavailable("The iFood test user must be authorized again")
                try:
                    refreshed = await refresh(settings, tokens.refresh_token)
                except OAuthTokenError as exc:
                    raise OAuthSessionUnavailable(
                        "The iFood test user refresh token is invalid; authorize it again"
                    ) from exc
                tokens = replace(
                    refreshed,
                    granted_scopes=refreshed.granted_scopes or tokens.granted_scopes,
                )
                store.put(session_id, tokens)

    return tokens.access_token
