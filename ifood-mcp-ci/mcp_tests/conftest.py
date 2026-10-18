from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SUITE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = SUITE_ROOT.parent
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.integrations.ifood.auth import EncryptedSQLiteOAuthTokenStore  # noqa: E402
from app.integrations.ifood.settings import IFoodMCPSettings  # noqa: E402
from mcp_tests.auth_session import get_valid_access_token  # noqa: E402


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    if os.getenv("IFOOD_MCP_LIVE_REQUIRED", "").lower() == "true":
        pytest.fail(f"Required live-test configuration is missing: {name}")
    pytest.skip(f"Live iFood MCP configuration is missing: {name}")


@pytest.fixture
def live_mcp_context():
    session_id = _required_environment("IFOOD_TEST_SESSION_ID")
    database_path = _required_environment("IFOOD_TOKEN_STORE_PATH")
    encryption_key = _required_environment("IFOOD_TOKEN_ENCRYPTION_KEY")

    settings = IFoodMCPSettings.from_environment()
    settings.validate()
    settings.validate_token_exchange()
    store = EncryptedSQLiteOAuthTokenStore(database_path, encryption_key)

    async def resolve() -> tuple[IFoodMCPSettings, str]:
        token = await get_valid_access_token(session_id, store, settings)
        return replace(settings, access_token=token), token

    return resolve
