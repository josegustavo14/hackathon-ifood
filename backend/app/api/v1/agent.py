from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.agent.llm_meal_plan import LLMInterpretationError, interpret_meal_plan
from app.agent.meal_plan_extractor import MealPlanParseError
from app.agent.pdf_parser import PdfExtractionError, extract_text
from app.models.agent import AgentRequest, AgentResponse
from app.models.recipe import MealPlan
from app.agent.service import AgentService

router = APIRouter(tags=["agent"])
MAX_PDF_BYTES = 10 * 1024 * 1024


@router.post("/agent/chat", response_model=AgentResponse)
async def chat(request: AgentRequest) -> AgentResponse:
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    settings = get_settings()
    session_id = request.session_id or str(uuid4())
    service = AgentService(provider=settings.llm_provider, api_key=settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url, timeout=settings.llm_timeout_seconds)
    return await service.chat(request.model_copy(update={"session_id": session_id}))


@router.post("/meal-plans/parse", response_model=MealPlan)
async def parse_meal_plan(file: Annotated[UploadFile, File()]) -> MealPlan:
    if not file.filename or not file.filename.lower().endswith(".pdf") or file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="A PDF file is required")
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MiB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF signature")
    try:
        text = extract_text(content)
        settings = get_settings()
        return await interpret_meal_plan(
            text,
            file.filename,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )
    except (PdfExtractionError, MealPlanParseError, LLMInterpretationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
