from enum import Enum

from pydantic import Field, model_validator

from .common import Contract, Money
from .shopping import ShoppingItem


class CartStatus(str, Enum):
    draft = "draft"
    ready_for_review = "ready_for_review"
    confirmed = "confirmed"
    applied = "applied"
    failed = "failed"


class CartProposal(Contract):
    id: str
    merchant_id: str | None = None
    address_id: str | None = None
    items: list[ShoppingItem]
    estimated_subtotal: Money
    currency: str = "BRL"
    requires_confirmation: bool = True
    status: CartStatus

    @model_validator(mode="after")
    def validate_currency(self):
        if self.currency != "BRL":
            raise ValueError("currency must be BRL")
        return self


class CartApplyRequest(Contract):
    proposal: CartProposal
    confirmed: bool


class CartApplyResponse(Contract):
    proposal: CartProposal
    mock_only: bool = True
    message: str
    cart_id: str | None = None
    app_deeplink: str | None = None
