from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.contracts import RecipeProvider
from app.core.dependencies import get_nutrition_provider, get_recipe_provider
from app.agent.llm_meal_plan import LLMInterpretationError, interpret_meal_plan
from app.agent.meal_plan_extractor import MealPlanParseError
from app.agent.pdf_parser import PdfExtractionError, extract_text
from app.models.agent import AgentRequest, AgentResponse
from app.models.recipe import MealPlan
from app.models.recipe import Recipe
from app.agent.service import AgentService
from app.nutrition.usda import USDAUpstreamError

router = APIRouter(tags=["agent"])
MAX_PDF_BYTES = 10 * 1024 * 1024


@router.post("/agent/chat", response_model=AgentResponse)
async def chat(request: AgentRequest, recipes: Annotated[RecipeProvider, Depends(get_recipe_provider)]) -> AgentResponse:
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    settings = get_settings()
    session_id = request.session_id or str(uuid4())
    service = AgentService(provider=settings.llm_provider, api_key=settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url, timeout=settings.llm_timeout_seconds, recipes=recipes)
    result = await service.chat(request.model_copy(update={"session_id": session_id}))
    if result.nutrition_requested and result.recipe:
        try:
            async for nutrition_provider in get_nutrition_provider():
                calculation = await nutrition_provider.calculate(result.recipe, result.recipe.servings)
                if calculation.per_serving:
                    result.nutrition = calculation.per_serving
                    result.message += " Estimativa nutricional por porção incluída."
                else:
                    result.message += " Não há dados suficientes para estimar a nutrição desta receita."
        except (USDAUpstreamError, HTTPException) as exc:
            result.message += f" A consulta nutricional está indisponível: {getattr(exc, 'message', getattr(exc, 'detail', 'erro na fonte'))}"
    return result


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
        plan = await interpret_meal_plan(
            text,
            file.filename,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            reasoning_effort=settings.llm_reasoning_effort,
        )
        required = [ingredient.model_copy(update={"id": f"meal-{meal_index}-{ingredient_index}-{ingredient.id}"})
                    for meal_index, meal in enumerate(plan.meals)
                    for ingredient_index, ingredient in enumerate(meal.ingredients)]
        if required:
            nutrition_recipe = Recipe(id=f"{plan.id}-required", name="Refeições obrigatórias extraídas", servings=1,
                                      ingredients=required, instructions=[], source="meal_plan")
            try:
                async for provider in get_nutrition_provider():
                    plan.nutrition = await provider.calculate(nutrition_recipe, 1)
            except (USDAUpstreamError, HTTPException) as exc:
                plan.extraction_warnings.append(f"Nutrição indisponível: {getattr(exc, 'message', getattr(exc, 'detail', 'erro na fonte'))}")
            plan.extraction_warnings.append("Nutrição considera cada refeição obrigatória extraída uma vez; alternativas e frequência semanal não entram na soma.")
        return plan
    except (PdfExtractionError, MealPlanParseError, LLMInterpretationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
