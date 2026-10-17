import os

from pydantic import BaseModel


class Settings(BaseModel):
    mock_mode: bool = True
    frontend_origin: str = "http://localhost:5173"
    nutrition_provider: str = "mock"
    usda_api_key: str = ""


def get_settings() -> Settings:
    return Settings(
        mock_mode=os.getenv("MOCK_MODE", "true").lower() in {"1", "true", "yes"},
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        nutrition_provider=os.getenv("NUTRITION_PROVIDER", "mock").lower(),
        usda_api_key=os.getenv("USDA_API_KEY", ""),
    )
