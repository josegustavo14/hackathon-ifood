from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import require_mock_mode
from app.models.cart import CartApplyRequest, CartApplyResponse, CartProposal, CartStatus
from app.models.common import Contract
from app.models.shopping import ShoppingList, ShoppingItemStatus
from app.mocks.data import load_json
from app.mocks.services import mock_proposal

router = APIRouter(prefix="/cart", tags=["cart"], dependencies=[Depends(require_mock_mode)])


class CartPreviewRequest(Contract):
    shopping_list: ShoppingList


@router.post("/preview", response_model=CartProposal)
async def preview_cart(request: CartPreviewRequest) -> CartProposal:
    if any(item.status != ShoppingItemStatus.matched for item in request.shopping_list.items):
        raise HTTPException(status_code=409, detail="Shopping list has unresolved items")
    return mock_proposal(request.shopping_list)


@router.post("/apply", response_model=CartApplyResponse)
async def apply_cart(request: CartApplyRequest) -> CartApplyResponse:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    if request.proposal.status != CartStatus.ready_for_review or not request.proposal.items:
        raise HTTPException(status_code=409, detail="Proposal is not ready for review")
    simulated = request.proposal.model_copy(update={"status": CartStatus.applied, "requires_confirmation": False})
    return CartApplyResponse(proposal=simulated, message=load_json("cart.json")["applied_message"])
