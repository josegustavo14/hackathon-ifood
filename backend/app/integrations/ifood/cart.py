"""Typed contracts and safety errors for the iFood Cart MCP."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import Money


class CartInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CartCustomizationInput(CartInput):
    customization_id: str = Field(alias="customizationId", min_length=1)
    quantity: int = Field(default=1, ge=1)
    customer_note: str | None = Field(default=None, alias="customerNote")


class CartOptionInput(CartInput):
    option_id: str = Field(alias="optionId", min_length=1)
    quantity: int = Field(default=1, ge=1)
    customer_note: str | None = Field(default=None, alias="customerNote")
    customizations: list[CartCustomizationInput] = Field(default_factory=list)


class CartItemInput(CartInput):
    """Catalog item sent to create/add/update Cart tools.

    ``options`` deliberately defaults to an empty array because the Cart MCP
    requires the key even for products without selectable options.
    """

    item_id: str = Field(alias="itemId", min_length=1)
    quantity: int = Field(default=1, ge=1)
    options: list[CartOptionInput] = Field(default_factory=list)
    customer_note: str | None = Field(default=None, alias="customerNote")

    def mcp_arguments(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class CartResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CartCustomization(CartResponse):
    customization_id: str = Field(alias="customizationId")
    name: str | None = None
    quantity: int = Field(ge=1)
    customer_note: str | None = Field(default=None, alias="customerNote")


class CartOption(CartResponse):
    option_id: str = Field(alias="optionId")
    name: str | None = None
    quantity: int = Field(ge=1)
    customer_note: str | None = Field(default=None, alias="customerNote")
    customizations: list[CartCustomization] = Field(default_factory=list)


class CartItem(CartResponse):
    item_id: str = Field(alias="itemId")
    cart_item_id: str | None = Field(default=None, alias="cartItemId")
    name: str
    quantity: int = Field(ge=1)
    unit_price: Money = Field(alias="unitPrice")
    customer_note: str | None = Field(default=None, alias="customerNote")
    options: list[CartOption] = Field(default_factory=list)


class CartMerchant(CartResponse):
    merchant_id: str = Field(alias="merchantId")
    merchant_name: str | None = Field(default=None, alias="merchantName")
    order_minimum_price: Money | None = Field(default=None, alias="orderMinimumPrice")
    formatted_address: str | None = Field(default=None, alias="formattedAddress")


class CartSummary(CartResponse):
    total_name: str = Field(alias="totalName")
    total_amount: Money = Field(alias="totalAmount")
    subtotal_name: str = Field(alias="subtotalName")
    subtotal_amount: Money = Field(alias="subtotalAmount")
    delivery_fee_name: str = Field(alias="deliveryFeeName")
    delivery_fee_amount: Money = Field(alias="deliveryFeeAmount")
    fee_total_name: str = Field(alias="feeTotalName")
    fee_total_amount: Money = Field(alias="feeTotalAmount")
    benefits_total_name: str = Field(alias="benefitsTotalName")
    benefits_total_amount: Money = Field(alias="benefitsTotalAmount")
    voucher_total_name: str = Field(alias="voucherTotalName")
    voucher_total_amount: Money = Field(alias="voucherTotalAmount")


class CartDetails(CartResponse):
    cart_id: str = Field(alias="cartId")
    merchant: CartMerchant | None = None
    items: list[CartItem] = Field(default_factory=list)
    delivery_address: dict[str, Any] | None = Field(default=None, alias="deliveryAddress")
    delivery_method: dict[str, Any] | None = Field(default=None, alias="deliveryMethod")
    payment_method: dict[str, Any] | None = Field(default=None, alias="paymentMethod")
    fees: list[dict[str, Any]] = Field(default_factory=list)
    summary: CartSummary | None = None
    warning: dict[str, Any] | None = None
    app_deeplink: str | None = Field(default=None, alias="appDeeplink")
    agent_hints: dict[str, Any] = Field(default_factory=dict, alias="agentHints")


class CartRemovalResult(CartResponse):
    """Result used when removing the last item also deletes the cart."""

    cart_deleted: bool = True
    agent_hints: dict[str, Any] = Field(default_factory=dict, alias="agentHints")


class CheckoutResult(CartResponse):
    order_id: str = Field(alias="orderId")
    agent_hints: dict[str, Any] = Field(default_factory=dict, alias="agentHints")
