from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.v1.router import router
from app.api.v1.ifood_auth import callback_router
from app.core.config import get_settings


class HealthResponse(BaseModel):
    status: str
    mock_mode: bool


app = FastAPI(title="iFood Chef AI API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().frontend_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(callback_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content=jsonable_encoder({"error": {"code": "validation_error", "message": "Invalid request", "details": exc.errors()}}))


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail), "details": []}})


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", mock_mode=get_settings().mock_mode)
