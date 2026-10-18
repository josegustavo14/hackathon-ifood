"""OAuth Authorization Code with PKCE helpers for the iFood consumer MCP.

The returned verifier is secret material. Store it server-side, keyed by
``state``, until the callback exchanges the authorization code for tokens.
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from time import time
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .settings import IFoodConfigurationError, IFoodMCPSettings


@dataclass(frozen=True, slots=True)
class PKCEAuthorizationRequest:
    authorization_url: str
    state: str
    code_verifier: str


class OAuthStateError(ValueError):
    """Raised when an OAuth callback cannot be tied to its original request."""


class OAuthTokenError(RuntimeError):
    """Raised when iFood refuses or malforms an authorization-code exchange."""


class OAuthRevocationError(RuntimeError):
    """Raised when iFood does not confirm token revocation."""


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None
    granted_scopes: frozenset[str] = frozenset()


OAUTH_SESSION_COOKIE = "ifood_oauth_session"


@dataclass(frozen=True, slots=True)
class _StoredTokens:
    tokens: OAuthTokens
    expires_at: float


class OAuthTokenStore:
    """In-memory token store used by isolated tests and mock deployments."""
    def __init__(self) -> None:
        self._tokens: dict[str, _StoredTokens] = {}
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    def put(self, browser_session_id: str, tokens: OAuthTokens) -> None:
        self._tokens[browser_session_id] = _StoredTokens(tokens=tokens, expires_at=monotonic() + tokens.expires_in)

    def get(self, browser_session_id: str) -> OAuthTokens | None:
        stored = self._tokens.get(browser_session_id)
        if stored is None:
            return None
        return stored.tokens

    def refresh_required(self, browser_session_id: str, leeway_seconds: int = 300) -> bool:
        stored = self._tokens.get(browser_session_id)
        return stored is not None and stored.expires_at <= monotonic() + leeway_seconds

    def refresh_lock(self, browser_session_id: str) -> asyncio.Lock:
        return self._refresh_locks.setdefault(browser_session_id, asyncio.Lock())

    def delete(self, browser_session_id: str) -> None:
        self._tokens.pop(browser_session_id, None)


class EncryptedSQLiteOAuthTokenStore:
    """Persistent encrypted token storage keyed by the HttpOnly session cookie.

    Only opaque Fernet ciphertext is written to SQLite. A new store instance can
    recover the OAuth session after a backend restart as long as the browser
    cookie and encryption secret remain unchanged.
    """

    def __init__(self, database_path: str | Path, encryption_secret: str) -> None:
        if not encryption_secret:
            raise IFoodConfigurationError("OAuth token encryption requires a non-empty secret")
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._cipher = Fernet(_fernet_key(encryption_secret))
        self._refresh_locks: dict[str, asyncio.Lock] = {}
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=5)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    browser_session_id TEXT PRIMARY KEY,
                    encrypted_tokens BLOB NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
        os.chmod(self.database_path, 0o600)

    def put(self, browser_session_id: str, tokens: OAuthTokens) -> None:
        payload = json.dumps(
            {
                "access_token": tokens.access_token,
                "token_type": tokens.token_type,
                "expires_in": tokens.expires_in,
                "refresh_token": tokens.refresh_token,
                "id_token": tokens.id_token,
                "granted_scopes": sorted(tokens.granted_scopes),
            },
            separators=(",", ":"),
        ).encode()
        encrypted = self._cipher.encrypt(payload)
        now = time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO oauth_tokens (
                    browser_session_id, encrypted_tokens, expires_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(browser_session_id) DO UPDATE SET
                    encrypted_tokens = excluded.encrypted_tokens,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (browser_session_id, encrypted, now + tokens.expires_in, now),
            )

    def get(self, browser_session_id: str) -> OAuthTokens | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_tokens FROM oauth_tokens WHERE browser_session_id = ?",
                (browser_session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(self._cipher.decrypt(row[0]))
            return OAuthTokens(
                access_token=payload["access_token"],
                token_type=payload["token_type"],
                expires_in=int(payload["expires_in"]),
                refresh_token=payload.get("refresh_token"),
                id_token=payload.get("id_token"),
                granted_scopes=frozenset(payload.get("granted_scopes", [])),
            )
        except (InvalidToken, KeyError, TypeError, ValueError, json.JSONDecodeError):
            # A key rotation or corrupt row invalidates only this session.
            self.delete(browser_session_id)
            return None

    def refresh_required(self, browser_session_id: str, leeway_seconds: int = 300) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM oauth_tokens WHERE browser_session_id = ?",
                (browser_session_id,),
            ).fetchone()
        return row is not None and float(row[0]) <= time() + leeway_seconds

    def refresh_lock(self, browser_session_id: str) -> asyncio.Lock:
        return self._refresh_locks.setdefault(browser_session_id, asyncio.Lock())

    def delete(self, browser_session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM oauth_tokens WHERE browser_session_id = ?",
                (browser_session_id,),
            )


def _fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def create_oauth_token_store() -> OAuthTokenStore | EncryptedSQLiteOAuthTokenStore:
    encryption_secret = (
        os.getenv("IFOOD_TOKEN_ENCRYPTION_KEY", "").strip()
        or os.getenv("IFOOD_CLIENT_SECRET", "").strip()
    )
    if not encryption_secret:
        return OAuthTokenStore()
    default_path = Path(__file__).resolve().parents[3] / ".data" / "ifood_oauth.sqlite3"
    database_path = os.getenv("IFOOD_TOKEN_STORE_PATH", "").strip() or default_path
    return EncryptedSQLiteOAuthTokenStore(database_path, encryption_secret)


oauth_token_store = create_oauth_token_store()


@dataclass(frozen=True, slots=True)
class _PendingAuthorization:
    state: str
    code_verifier: str
    browser_session_id: str
    expires_at: float


class PKCEAuthorizationStore:
    """One-time, in-memory authorization state store.

    A production deployment with more than one process must replace this with a
    shared TTL store (for example Redis). It deliberately stores no access or
    refresh tokens.
    """
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl_seconds = ttl_seconds
        self._pending: dict[str, _PendingAuthorization] = {}

    def begin(self, settings: IFoodMCPSettings, browser_session_id: str) -> PKCEAuthorizationRequest:
        self._remove_expired()
        request = create_pkce_authorization_request(settings)
        self._pending[request.state] = _PendingAuthorization(
            state=request.state, code_verifier=request.code_verifier,
            browser_session_id=browser_session_id, expires_at=monotonic() + self._ttl_seconds,
        )
        return request

    def consume_callback(self, state: str, browser_session_id: str | None) -> str:
        self._remove_expired()
        pending = self._pending.get(state)
        if pending is None or browser_session_id is None:
            raise OAuthStateError("Invalid or expired OAuth state")
        if not secrets.compare_digest(state, pending.state) or not secrets.compare_digest(browser_session_id, pending.browser_session_id):
            raise OAuthStateError("Invalid OAuth state")
        del self._pending[state]
        return pending.code_verifier

    def _remove_expired(self) -> None:
        now = monotonic()
        expired = [state for state, item in self._pending.items() if item.expires_at <= now]
        for state in expired:
            del self._pending[state]


def create_pkce_authorization_request(settings: IFoodMCPSettings) -> PKCEAuthorizationRequest:
    """Generate a one-time PKCE request for redirecting the current user.

    ``code_verifier`` must never be sent to the browser as a query parameter or
    persisted in a client-side store.
    """
    settings.validate_authorization()
    code_verifier = _base64url(secrets.token_bytes(32))
    code_challenge = _base64url(hashlib.sha256(code_verifier.encode("ascii")).digest())
    state = _base64url(secrets.token_bytes(24))
    parameters = {
        "response_type": "code",
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if settings.scope:
        parameters["scope"] = settings.scope
    return PKCEAuthorizationRequest(
        authorization_url=f"{settings.authorize_url}?{urlencode(parameters)}",
        state=state,
        code_verifier=code_verifier,
    )


async def exchange_authorization_code(
    settings: IFoodMCPSettings,
    authorization_code: str,
    code_verifier: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> OAuthTokens:
    """Exchange a validated authorization code without exposing client secrets."""
    settings.validate_token_exchange()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
    try:
        response = await active_client.post(
            settings.token_url or "",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": settings.redirect_uri or "",
                "client_id": settings.client_id or "",
                "client_secret": settings.client_secret or "",
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        if response.is_error:
            raise OAuthTokenError("iFood rejected the authorization-code exchange")
        return _parse_tokens(response)
    finally:
        if owns_client:
            await active_client.aclose()


async def refresh_access_token(
    settings: IFoodMCPSettings,
    refresh_token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> OAuthTokens:
    """Rotate an expired user token using its server-side refresh token."""
    settings.validate_token_exchange()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
    try:
        response = await active_client.post(
            settings.token_url or "",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.client_id or "",
                "client_secret": settings.client_secret or "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        if response.is_error:
            raise OAuthTokenError("iFood rejected the refresh-token exchange")
        return _parse_tokens(response)
    finally:
        if owns_client:
            await active_client.aclose()


async def revoke_token(
    settings: IFoodMCPSettings,
    token: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Immediately revoke an iFood refresh or access token from the backend."""
    settings.validate_revocation()
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
    try:
        response = await active_client.post(
            settings.revoke_url or "",
            data={
                "token": token,
                "client_id": settings.client_id or "",
                "client_secret": settings.client_secret or "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        if response.status_code != 200:
            raise OAuthRevocationError("iFood rejected token revocation")
    finally:
        if owns_client:
            await active_client.aclose()


def _parse_tokens(response: httpx.Response) -> OAuthTokens:
    try:
        payload: Any = response.json()
    except ValueError as exc:
        raise OAuthTokenError("iFood token endpoint returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OAuthTokenError("iFood token endpoint returned an invalid payload")
    access_token = payload.get("access_token")
    token_type = payload.get("token_type")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not access_token or not isinstance(token_type, str):
        raise OAuthTokenError("iFood token response is missing access_token or token_type")
    if token_type.casefold() != "bearer":
        raise OAuthTokenError("iFood token response has an unsupported token_type")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise OAuthTokenError("iFood token response is missing the rotated refresh_token")
    try:
        expires_in = int(expires_in)
    except (TypeError, ValueError) as exc:
        raise OAuthTokenError("iFood token response has an invalid expires_in") from exc
    if expires_in <= 0:
        raise OAuthTokenError("iFood token response has an invalid expires_in")
    return OAuthTokens(
        access_token=access_token, token_type=token_type, expires_in=expires_in,
        refresh_token=refresh_token,
        id_token=payload.get("id_token") if isinstance(payload.get("id_token"), str) else None,
        granted_scopes=parse_scopes(payload.get("scope")),
    )


def parse_scopes(value: Any) -> frozenset[str]:
    if not isinstance(value, str):
        return frozenset()
    return frozenset(scope for scope in value.split() if scope)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
