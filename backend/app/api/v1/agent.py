from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import require_mock_mode
from app.models.agent import AgentRequest, AgentResponse
from app.models.recipe import MealPlan
from app.mocks.data import load_json, meal_plan

router = APIRouter(tags=["agent"], dependencies=[Depends(require_mock_mode)])
MAX_PDF_BYTES = 10 * 1024 * 1024


@router.post("/agent/chat", response_model=AgentResponse)
async def chat(request: AgentRequest) -> AgentResponse:
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    return AgentResponse(session_id=request.session_id or str(uuid4()), **load_json("agent.json"))


@router.post("/meal-plans/parse", response_model=MealPlan)
async def parse_meal_plan(file: Annotated[UploadFile, File()]) -> MealPlan:
    if not file.filename or not file.filename.lower().endswith(".pdf") or file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="A PDF file is required")
    content = await file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MiB")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF signature")
    return meal_plan(file.filename)
