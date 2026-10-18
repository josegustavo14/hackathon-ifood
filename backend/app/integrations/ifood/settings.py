"""Configuration local to the iFood MCP integration.

Secrets are intentionally read only from environment variables.  The frontend
must never receive an iFood access token or client secret.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class IFoodMCPSettings:
    mcp_url: str
    authorize_url: str | None
    redirect_uri: str | None
    client_id: str | None
    client_secret: str | None
    token_url: str | None
    revoke_url: str | None
    access_token: str | None
    scope: str | None
    timeout_seconds: float
    session_cookie_max_age_seconds: int

    @classmethod
    def from_environment(cls) -> "IFoodMCPSettings":
        return cls(
            mcp_url=os.getenv("IFOOD_MCP_URL", "").strip(),
            authorize_url=os.getenv("IFOOD_OAUTH_AUTHORIZE_URL") or None,
            redirect_uri=os.getenv("IFOOD_OAUTH_REDIRECT_URI") or None,
            client_id=os.getenv("IFOOD_CLIENT_ID") or None,
            client_secret=os.getenv("IFOOD_CLIENT_SECRET") or None,
            token_url=os.getenv("IFOOD_TOKEN_URL") or None,
            revoke_url=os.getenv("IFOOD_REVOKE_URL") or None,
            access_token=os.getenv("IFOOD_ACCESS_TOKEN") or None,
            scope=os.getenv("IFOOD_MCP_SCOPE") or None,
            timeout_seconds=float(os.getenv("IFOOD_MCP_TIMEOUT_SECONDS", "15")),
            session_cookie_max_age_seconds=int(os.getenv("IFOOD_SESSION_COOKIE_MAX_AGE_SECONDS", "2592000")),
        )

    def validate(self) -> None:
        if not self.mcp_url:
            raise IFoodConfigurationError("IFOOD_MCP_URL is required when MOCK_MODE=false")
        _validate_secure_url("IFOOD_MCP_URL", self.mcp_url)

    def validate_authorization(self) -> None:
        if not self.authorize_url or not self.client_id or not self.redirect_uri:
            raise IFoodConfigurationError(
                "OAuth authorization requires IFOOD_OAUTH_AUTHORIZE_URL, IFOOD_CLIENT_ID and IFOOD_OAUTH_REDIRECT_URI"
            )
        _validate_secure_url("IFOOD_OAUTH_AUTHORIZE_URL", self.authorize_url)
        _validate_secure_url("IFOOD_OAUTH_REDIRECT_URI", self.redirect_uri)
        if self.session_cookie_max_age_seconds <= 0:
            raise IFoodConfigurationError("IFOOD_SESSION_COOKIE_MAX_AGE_SECONDS must be positive")

    def validate_token_exchange(self) -> None:
        if not self.token_url or not self.client_id or not self.client_secret or not self.redirect_uri:
            raise IFoodConfigurationError(
                "Token exchange requires IFOOD_TOKEN_URL, IFOOD_CLIENT_ID, IFOOD_CLIENT_SECRET and IFOOD_OAUTH_REDIRECT_URI"
            )
        _validate_secure_url("IFOOD_TOKEN_URL", self.token_url)
        _validate_secure_url("IFOOD_OAUTH_REDIRECT_URI", self.redirect_uri)

    def validate_revocation(self) -> None:
        if not self.revoke_url or not self.client_id or not self.client_secret:
            raise IFoodConfigurationError(
                "Token revocation requires IFOOD_REVOKE_URL, IFOOD_CLIENT_ID and IFOOD_CLIENT_SECRET"
            )
        _validate_secure_url("IFOOD_REVOKE_URL", self.revoke_url)

    @property
    def secure_cookie(self) -> bool:
        return bool(self.redirect_uri and urlparse(self.redirect_uri).scheme == "https")


class IFoodConfigurationError(RuntimeError):
    """Raised before a request when the real integration is not configured."""


def _validate_secure_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.hostname:
        return
    if parsed.scheme == "http" and parsed.hostname == "localhost":
        return
    raise IFoodConfigurationError(f"{name} must use HTTPS; only localhost may use HTTP")
