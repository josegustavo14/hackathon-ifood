from decimal import Decimal

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.models.cart import CartApplyRequest, CartApplyResponse, CartProposal, CartStatus
from app.models.common import Contract
from app.models.shopping import ShoppingList, ShoppingItemStatus
from app.mocks.data import load_json
from app.mocks.services import mock_proposal

router = APIRouter(prefix="/cart", tags=["cart"])


class CartPreviewRequest(Contract):
    shopping_list: ShoppingList


@router.post("/preview", response_model=CartProposal)
async def preview_cart(request: CartPreviewRequest) -> CartProposal:
    if any(item.status != ShoppingItemStatus.matched for item in request.shopping_list.items):
        raise HTTPException(status_code=409, detail="Shopping list has unresolved items")
    if not request.shopping_list.items:
        raise HTTPException(status_code=409, detail="Shopping list is empty")
    if any(item.selected_product is None or not item.selected_product.available or item.purchase_quantity <= 0 or
           item.total_price != item.selected_product.price * item.purchase_quantity for item in request.shopping_list.items):
        raise HTTPException(status_code=409, detail="Shopping list contains invalid product or price data")
    subtotal = sum((item.total_price for item in request.shopping_list.items), Decimal("0.00"))
    if subtotal != request.shopping_list.estimated_subtotal:
        raise HTTPException(status_code=409, detail="Shopping list subtotal does not match selected items")
    if get_settings().mock_mode:
        return mock_proposal(request.shopping_list)
    merchant_ids = {item.selected_product.merchant_id for item in request.shopping_list.items if item.selected_product}
    if len(merchant_ids) != 1:
        raise HTTPException(status_code=409, detail="A cart proposal must contain products from one merchant")
    return CartProposal(
        id=f"proposal-{request.shopping_list.id}", merchant_id=next(iter(merchant_ids)),
        items=request.shopping_list.items, estimated_subtotal=subtotal,
        requires_confirmation=True, status=CartStatus.ready_for_review,
    )


@router.post("/apply", response_model=CartApplyResponse)
async def apply_cart(request: CartApplyRequest) -> CartApplyResponse:
    if not get_settings().mock_mode:
        raise HTTPException(status_code=503, detail="Cart write tools are not available for this iFood connection; no real cart was changed")
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    if request.proposal.status != CartStatus.ready_for_review or not request.proposal.items:
        raise HTTPException(status_code=409, detail="Proposal is not ready for review")
    simulated = request.proposal.model_copy(update={"status": CartStatus.applied, "requires_confirmation": False})
    return CartApplyResponse(proposal=simulated, message=load_json("cart.json")["applied_message"])
