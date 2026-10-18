from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_settings
from app.core.contracts import IFoodGateway
from app.core.dependencies import get_ifood_gateway
from app.integrations.ifood.cart import CartItemInput
from app.integrations.ifood.mcp import MCPAuthenticationError, MCPAuthorizationError, MCPError
from app.integrations.ifood.models import AvailabilityStatus
from app.models.cart import (
    CartApplyRequest, CartApplyResponse, CartCheckoutRequest, CartCheckoutResponse,
    CartProposal, CartStatus,
)
from app.models.common import Contract
from app.models.shopping import ShoppingList, ShoppingItemStatus
from app.mocks.data import load_json
from app.mocks.services import mock_proposal

router = APIRouter(prefix="/cart", tags=["cart"])


class CartPreviewRequest(Contract):
    shopping_list: ShoppingList
    address_id: str | None = None


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
    if not request.address_id:
        raise HTTPException(status_code=422, detail="A saved delivery address is required for a real cart proposal")
    return CartProposal(
        id=f"proposal-{request.shopping_list.id}", merchant_id=next(iter(merchant_ids)), address_id=request.address_id,
        items=request.shopping_list.items, estimated_subtotal=subtotal,
        requires_confirmation=True, status=CartStatus.ready_for_review,
    )


@router.post("/apply", response_model=CartApplyResponse)
async def apply_cart(request: CartApplyRequest, gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)]) -> CartApplyResponse:
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit confirmation is required")
    proposal = request.proposal
    if proposal.status != CartStatus.ready_for_review or not proposal.items or not proposal.requires_confirmation:
        raise HTTPException(status_code=409, detail="Proposal is not ready for review")
    if get_settings().mock_mode:
        simulated = proposal.model_copy(update={"status": CartStatus.applied, "requires_confirmation": False})
        return CartApplyResponse(proposal=simulated, message=load_json("cart.json")["applied_message"])
    if not proposal.merchant_id or not proposal.address_id:
        raise HTTPException(status_code=422, detail="Merchant and saved delivery address are required")
    if any(item.status != ShoppingItemStatus.matched or not item.selected_product or
           item.selected_product.merchant_id != proposal.merchant_id or
           item.selected_product.source != "ifood_mcp" or not item.selected_product.available or
           item.purchase_quantity <= 0 or item.total_price != item.selected_product.price * item.purchase_quantity
           for item in proposal.items):
        raise HTTPException(status_code=409, detail="Proposal contains invalid or non-iFood products")
    subtotal = sum((item.total_price for item in proposal.items), Decimal("0.00"))
    if subtotal != proposal.estimated_subtotal:
        raise HTTPException(status_code=409, detail="Proposal subtotal does not match its items")
    try:
        tools = await gateway.list_tools()
        if "createCart" not in {tool.get("name") for tool in tools}:
            raise HTTPException(status_code=503, detail="The iFood session does not expose createCart")
        addresses = await gateway.list_addresses()
        if proposal.address_id not in {address.address_id for address in addresses.addresses}:
            raise HTTPException(status_code=409, detail="Delivery address is not saved in this iFood account")
        quantities: dict[str, int] = {}
        checked_prices: dict[str, Decimal] = {}
        for item in proposal.items:
            product = item.selected_product
            if product.id not in checked_prices:
                current = await gateway.get_item(product.id, proposal.merchant_id, address_id=proposal.address_id)
                if current.availability != AvailabilityStatus.available or current.price != product.price:
                    raise HTTPException(status_code=409, detail=f"Product {product.id} changed price or availability; review the proposal again")
                checked_prices[product.id] = product.price
            elif checked_prices[product.id] != product.price:
                raise HTTPException(status_code=409, detail=f"Product {product.id} has conflicting prices")
            quantities[product.id] = quantities.get(product.id, 0) + item.purchase_quantity
        cart = await gateway.create_cart(proposal.merchant_id, proposal.address_id, [
            CartItemInput(itemId=item_id, quantity=quantity) for item_id, quantity in sorted(quantities.items())
        ])
        pix_selected = False
        tool_names = {tool.get("name") for tool in tools}
        if {"getCart", "setCartPayment"}.issubset(tool_names):
            pix_selected = await gateway.select_pix_payment(cart.cart_id)
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied cart access for this OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail="iFood could not create the cart; check your iFood account before retrying") from exc
    applied = proposal.model_copy(update={"status": CartStatus.applied, "requires_confirmation": False})
    payment_message = ("PIX selecionado no carrinho; conclua o pagamento somente no iFood."
                       if pix_selected else
                       "O iFood não forneceu uma opção PIX selecionável; escolha o pagamento no iFood.")
    return CartApplyResponse(proposal=applied, mock_only=False, cart_id=cart.cart_id,
                             app_deeplink=cart.app_deeplink,
                             message=f"Itens adicionados a um carrinho no iFood. {payment_message} Nenhum pedido foi enviado.")


@router.post("/checkout", response_model=CartCheckoutResponse)
async def checkout_cart(
    request: CartCheckoutRequest,
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
) -> CartCheckoutResponse:
    """Send checkout only after a second explicit user confirmation."""
    if not request.confirmed:
        raise HTTPException(status_code=409, detail="Explicit checkout confirmation is required")
    if get_settings().mock_mode:
        raise HTTPException(status_code=409, detail="Mock mode does not submit orders or payments")
    try:
        tool_names = {tool.get("name") for tool in await gateway.list_tools()}
        if "ifood_submitOrder" not in tool_names:
            raise HTTPException(
                status_code=503,
                detail="The authenticated iFood session does not expose checkout; no order was submitted",
            )
        result = await gateway.submit_order(request.cart_id, confirmed=True)
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied checkout access for this OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail="iFood could not complete checkout; no retry was made") from exc
    message = "Pedido enviado ao iFood."
    if result.payment_url:
        message += " Abra o link retornado para concluir o PIX."
    elif result.pix_qr_code:
        message += " Use o QR PIX retornado pelo iFood para concluir o pagamento."
    else:
        message += " O iFood não retornou link ou QR PIX; conclua o pagamento no app."
    return CartCheckoutResponse(order_id=result.order_id, payment_url=result.payment_url,
                                pix_qr_code=result.pix_qr_code, message=message)
