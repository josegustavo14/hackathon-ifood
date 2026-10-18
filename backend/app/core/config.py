import os

from pydantic import BaseModel


class Settings(BaseModel):
    mock_mode: bool = True
    frontend_origin: str = "http://localhost:5173"
    nutrition_provider: str = "mock"
    usda_api_key: str = ""
    llm_provider: str = "deterministic"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_reasoning_effort: str = ""
    llm_timeout_seconds: float = 45.0


def get_settings() -> Settings:
    def env(name: str, default: str = "") -> str:
        return os.getenv(name, default).strip()

    return Settings(
        mock_mode=env("MOCK_MODE", "true").lower() in {"1", "true", "yes"},
        frontend_origin=env("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/"),
        nutrition_provider=env("NUTRITION_PROVIDER", "mock").lower(),
        usda_api_key=env("USDA_API_KEY"),
        llm_provider=env("LLM_PROVIDER", "deterministic").lower(),
        llm_api_key=env("LLM_API_KEY"),
        llm_model=env("LLM_MODEL"),
        llm_base_url=env("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_reasoning_effort=env("LLM_REASONING_EFFORT").lower(),
        llm_timeout_seconds=float(env("LLM_TIMEOUT_SECONDS", "45")),
    )
