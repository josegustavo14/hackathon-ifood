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
    llm_timeout_seconds: float = 45.0


def get_settings() -> Settings:
    return Settings(
        mock_mode=os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes"},
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        nutrition_provider=os.getenv("NUTRITION_PROVIDER", "mock").lower(),
        usda_api_key=os.getenv("USDA_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "deterministic").lower(),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
    )
