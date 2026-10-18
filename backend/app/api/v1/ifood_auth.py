"""Browser-facing OAuth endpoints for connecting a user to iFood."""

import secrets
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.integrations.ifood.auth import (
    OAuthStateError,
    OAuthRevocationError,
    OAuthTokenError,
    OAUTH_SESSION_COOKIE,
    PKCEAuthorizationStore,
    exchange_authorization_code,
    oauth_token_store,
    parse_scopes,
    revoke_token,
)
from app.integrations.ifood.settings import IFoodConfigurationError, IFoodMCPSettings

router = APIRouter(prefix="/ifood/oauth", tags=["ifood"])
callback_router = APIRouter(tags=["ifood"])
_authorization_store = PKCEAuthorizationStore()
_SESSION_COOKIE = OAUTH_SESSION_COOKIE


class OAuthCallbackResponse(BaseModel):
    status: str
    message: str


class OAuthLogoutResponse(BaseModel):
    status: str
    message: str


@router.get("/authorize", status_code=307)
async def authorize() -> RedirectResponse:
    """Create the PKCE state server-side and redirect the browser to iFood."""
    try:
        settings = IFoodMCPSettings.from_environment()
        browser_session_id = secrets.token_urlsafe(32)
        request = _authorization_store.begin(settings, browser_session_id)
    except IFoodConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response = RedirectResponse(request.authorization_url, status_code=307)
    response.set_cookie(
        _SESSION_COOKIE, browser_session_id, max_age=600, httponly=True,
        secure=settings.secure_cookie, samesite="lax",
    )
    return response


@callback_router.get("/callback", response_model=OAuthCallbackResponse)
@router.get("/callback", response_model=OAuthCallbackResponse, include_in_schema=False)
async def callback(
    response: Response,
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=8)],
    scope: Annotated[str | None, Query()] = None,
    browser_session_id: Annotated[str | None, Cookie(alias=_SESSION_COOKIE)] = None,
) -> OAuthCallbackResponse:
    """Validate and consume the single-use OAuth state before token exchange."""
    try:
        code_verifier = _authorization_store.consume_callback(state, browser_session_id)
    except OAuthStateError as exc:
        raise HTTPException(status_code=403, detail="Invalid OAuth state. Possible CSRF attack.") from exc
    try:
        settings = IFoodMCPSettings.from_environment()
        tokens = await exchange_authorization_code(settings, code, code_verifier)
    except IFoodConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OAuthTokenError as exc:
        raise HTTPException(status_code=502, detail="iFood token exchange failed") from exc
    if browser_session_id is None:  # narrowed by consume_callback, kept for type safety.
        raise HTTPException(status_code=403, detail="Invalid OAuth state. Possible CSRF attack.")
    # Scopes are metadata only. Authorization is enforced by the iFood MCP
    # when each tool is invoked; the client must not infer permissions from a
    # locally maintained list of scope names.
    reported_scopes = tokens.granted_scopes or parse_scopes(scope) or parse_scopes(settings.scope)
    tokens = replace(tokens, granted_scopes=reported_scopes)
    oauth_token_store.put(browser_session_id, tokens)
    response.set_cookie(
        _SESSION_COOKIE, browser_session_id,
        max_age=settings.session_cookie_max_age_seconds,
        httponly=True, secure=settings.secure_cookie, samesite="lax",
    )
    return OAuthCallbackResponse(status="connected", message="iFood authorization completed")


@router.post("/logout", response_model=OAuthLogoutResponse)
async def logout(
    response: Response,
    browser_session_id: Annotated[str | None, Cookie(alias=_SESSION_COOKIE)] = None,
) -> OAuthLogoutResponse:
    """Revoke the current user's tokens and remove their local OAuth session."""
    if browser_session_id:
        async with oauth_token_store.refresh_lock(browser_session_id):
            tokens = oauth_token_store.get(browser_session_id)
            if tokens:
                token = tokens.refresh_token or tokens.access_token
                try:
                    await revoke_token(IFoodMCPSettings.from_environment(), token)
                except IFoodConfigurationError as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
                except OAuthRevocationError as exc:
                    raise HTTPException(status_code=502, detail="iFood token revocation failed") from exc
                oauth_token_store.delete(browser_session_id)
    settings = IFoodMCPSettings.from_environment()
    response.delete_cookie(
        _SESSION_COOKIE, path="/", httponly=True,
        secure=settings.secure_cookie, samesite="lax",
    )
    return OAuthLogoutResponse(status="disconnected", message="iFood authorization revoked")
