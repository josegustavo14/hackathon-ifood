"""Adapter between iFood's MCP tool results and the shared application contract."""

from decimal import Decimal, InvalidOperation
from dataclasses import replace
import re
from typing import Any

from app.models.ingredient import Unit
from app.models.product import ProductCandidate

from .cart import (
    CartDetails,
    CartItemInput,
    CartOptionInput,
    CartRemovalResult,
    CheckoutResult,
)
from .mcp import (
    MCPAuthenticationError, MCPAuthorizationError, MCPProtocolError,
    MCPToolError, StreamableHTTPMCPClient,
)
from .models import (
    AddressListResponse,
    AvailabilityStatus,
    DeliveryAddress,
    ItemDetailsResult,
    MCPToolResult,
    MerchantDetailsResult,
    MerchantType,
    OfferRefinements,
    OfferResultKind,
)
from .settings import IFoodConfigurationError, IFoodMCPSettings

_BROWSE_OFFERS_TOOL = "browseOffers"
_SEARCH_OFFERS_TOOL = "searchOffers"
_GET_ITEM_TOOL = "getItem"
_GET_MERCHANT_TOOL = "getMerchant"
_LIST_ADDRESSES_TOOL = "listAddresses"
_CREATE_CART_TOOL = "createCart"
_GET_CART_TOOL = "getCart"
_ADD_CART_ITEM_TOOL = "addItemToCart"
_UPDATE_CART_ITEM_TOOL = "updateCartItem"
_REMOVE_CART_ITEM_TOOL = "removeItemFromCart"
_SUBMIT_ORDER_TOOL = "ifood_submitOrder"


class IFoodMCPGateway:
    """Real iFood implementation of ``IFoodGateway``.

    Product data is normalized at this boundary so the rest of the application
    keeps its stable, BRL-only Pydantic contract.
    """

    def __init__(
        self,
        settings: IFoodMCPSettings,
        client: StreamableHTTPMCPClient | None = None,
    ) -> None:
        settings.validate()
        self._settings = settings
        self._client = client or StreamableHTTPMCPClient(settings)

    @classmethod
    def from_environment(
        cls,
        access_token: str | None = None,
    ) -> "IFoodMCPGateway":
        settings = IFoodMCPSettings.from_environment()
        return cls(replace(settings, access_token=access_token) if access_token else settings)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return the tools actually exposed to the authenticated token."""
        return await self._client.list_tools()

    async def list_addresses(self) -> AddressListResponse:
        """Mandatory first call before any location-dependent discovery flow."""
        payload = await self._client.call_tool(_LIST_ADDRESSES_TOOL, {})
        if not isinstance(payload, dict):
            raise ValueError("listAddresses returned an invalid payload")
        _raise_mcp_errors(payload)
        raw_addresses = payload.get("results", [])
        if not isinstance(raw_addresses, list):
            raise ValueError("listAddresses returned an invalid results field")
        addresses = [DeliveryAddress.model_validate(item) for item in raw_addresses if isinstance(item, dict)]
        hints = payload.get("agentHints", {})
        return AddressListResponse(addresses=addresses, agent_hints=hints if isinstance(hints, dict) else {})

    async def search_offers(
        self, query: str, *, merchant_type: MerchantType | None = MerchantType.GROCERIES,
        address_id: str | None = None, latitude: float | None = None,
        longitude: float | None = None, result_kind: OfferResultKind = OfferResultKind.MERCHANT,
        refinements: OfferRefinements | None = None, page_size: int = 10,
        next_page_token: str | None = None,
    ) -> MCPToolResult:
        if not query.strip():
            raise ValueError("query must contain a descriptive search term")
        if not 1 <= page_size <= 25:
            raise ValueError("page_size must be between 1 and 25")
        arguments: dict[str, Any] = {
            "query": query,
            "resultKind": result_kind.value,
            "userLocation": await self._resolve_user_location(address_id, latitude, longitude),
            "pageSize": page_size,
        }
        if merchant_type:
            arguments["merchantType"] = merchant_type.value
        if refinements:
            arguments["refinements"] = refinements.mcp_arguments()
        if next_page_token:
            arguments["nextPageToken"] = next_page_token
        payload = await self._call_tool(_SEARCH_OFFERS_TOOL, arguments)
        _validate_offer_response(payload, result_kind)
        return MCPToolResult(tool=_SEARCH_OFFERS_TOOL, data=payload)

    async def browse_offers(
        self, *, merchant_type: MerchantType,
        address_id: str | None = None, latitude: float | None = None,
        longitude: float | None = None, result_kind: OfferResultKind = OfferResultKind.MERCHANT,
        refinements: OfferRefinements | None = None, page_size: int = 10,
        next_page_token: str | None = None,
    ) -> MCPToolResult:
        if not 1 <= page_size <= 25:
            raise ValueError("page_size must be between 1 and 25")
        arguments: dict[str, Any] = {
            "merchantType": merchant_type.value,
            "resultKind": result_kind.value,
            "userLocation": await self._resolve_user_location(address_id, latitude, longitude),
            "pageSize": page_size,
        }
        if refinements:
            arguments["refinements"] = refinements.mcp_arguments(browse=True)
        if next_page_token:
            arguments["nextPageToken"] = next_page_token
        payload = await self._call_tool(_BROWSE_OFFERS_TOOL, arguments)
        _validate_offer_response(payload, result_kind)
        return MCPToolResult(tool=_BROWSE_OFFERS_TOOL, data=payload)

    async def search_products(
        self, query: str, merchant_id: str | None = None, *,
        address_id: str | None = None, latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[ProductCandidate]:
        refinements = OfferRefinements(merchant_id=merchant_id) if merchant_id else None
        result = await self.search_offers(
            query, merchant_type=MerchantType.GROCERIES, result_kind=OfferResultKind.ITEM,
            refinements=refinements, address_id=address_id, latitude=latitude, longitude=longitude,
        )
        payload = result.data
        products = []
        for item in _records(payload, ("results",)):
            item_id = _string(item, "itemId")
            item_merchant = item.get("merchant") if isinstance(item.get("merchant"), dict) else {}
            resolved_merchant_id = _string(item_merchant, "merchantId") or merchant_id
            name = _string(item, "itemName")
            unit_price = _decimal(item.get("unitPrice"))
            promotional_price = _decimal(item.get("promotionalUnitPrice"))
            price = promotional_price if promotional_price is not None else unit_price
            if not item_id or not resolved_merchant_id or not name or price is None:
                continue
            package = _package_from_name(name)
            image = _string(item, "itemImageUrl")
            candidate = {
                "id": item_id, "merchant_id": resolved_merchant_id, "name": name,
                "merchant_name": _string(item_merchant, "merchantName"),
                "description": _string(item, "itemDescription"), "price": price,
                "currency": "BRL", "available": True,
                "package_quantity": package[0] if package else None,
                "package_unit": package[1] if package else None,
                "image_url": image, "source": "ifood_mcp",
            }
            try:
                products.append(ProductCandidate.model_validate(candidate))
            except ValueError:
                candidate["image_url"] = None
                products.append(ProductCandidate.model_validate(candidate))
        return products

    async def get_item(
        self, item_id: str, merchant_id: str, *, address_id: str | None = None,
        latitude: float | None = None, longitude: float | None = None,
    ) -> ItemDetailsResult:
        arguments = {
            "itemId": item_id,
            "merchantId": merchant_id,
            "userLocation": await self._resolve_user_location(address_id, latitude, longitude),
        }
        try:
            payload = await self._call_tool(_GET_ITEM_TOOL, arguments)
        except MCPToolError as exc:
            if exc.code == "ITEM_NOT_FOUND":
                return ItemDetailsResult(
                    tool=_GET_ITEM_TOOL, data=exc.payload,
                    item_id=item_id, merchant_id=merchant_id,
                    availability=AvailabilityStatus.unavailable,
                )
            raise
        item = payload if isinstance(payload, dict) else {}
        returned_item_id = _string(item, "itemId")
        returned_merchant_id = _string(item, "merchantId")
        if returned_item_id != item_id or returned_merchant_id != merchant_id:
            raise MCPProtocolError("ifood_getItem returned identifiers that do not match the request")
        unit_price = _decimal(item.get("unitPrice"))
        promotional_price = _decimal(item.get("promotionalUnitPrice"))
        item_name = _string(item, "itemName")
        if unit_price is None or item_name is None:
            raise MCPProtocolError("ifood_getItem response is missing itemName or unitPrice")
        return ItemDetailsResult(
            tool=_GET_ITEM_TOOL, data=payload, item_id=item_id,
            merchant_id=_string(item, "merchantId") or merchant_id,
            name=item_name, unit_price=unit_price,
            promotional_unit_price=promotional_price,
            price=promotional_price if promotional_price is not None else unit_price,
            currency="BRL", availability=AvailabilityStatus.available,
        )

    async def get_merchant(
        self, merchant_id: str, *, address_id: str | None = None,
        latitude: float | None = None, longitude: float | None = None,
    ) -> MerchantDetailsResult:
        payload = await self._call_tool(
            _GET_MERCHANT_TOOL,
            {
                "merchantId": merchant_id,
                "userLocation": await self._resolve_user_location(address_id, latitude, longitude),
            },
        )
        merchant = payload if isinstance(payload, dict) else {}
        if _string(merchant, "merchantId") != merchant_id:
            raise MCPProtocolError("ifood_getMerchant returned an identifier that does not match the request")
        raw_type = _string(merchant, "merchantType")
        try:
            merchant_type = MerchantType(raw_type) if raw_type else None
        except ValueError as exc:
            raise MCPProtocolError("ifood_getMerchant returned an invalid merchantType") from exc
        return MerchantDetailsResult(
            tool=_GET_MERCHANT_TOOL, data=payload, merchant_id=merchant_id,
            name=_string(merchant, "merchantName"),
            merchant_type=merchant_type,
            is_open=merchant.get("isOpen") if isinstance(merchant.get("isOpen"), bool) else None,
            minimum_order_amount=_decimal(merchant.get("minimumOrderAmount")),
        )

    async def create_cart(
        self,
        merchant_id: str,
        address_id: str,
        items: list[CartItemInput],
    ) -> CartDetails:
        """Create a cart from catalog item IDs returned by Offer Discovery."""
        if not merchant_id.strip() or not address_id.strip():
            raise ValueError("merchant_id and address_id are required")
        if not items:
            raise ValueError("at least one cart item is required")
        payload = await self._call_tool(
            _CREATE_CART_TOOL,
            {
                "merchantId": merchant_id,
                "addressId": address_id,
                "items": [item.mcp_arguments() for item in items],
            },
        )
        try:
            return _parse_cart(payload, _CREATE_CART_TOOL)
        except MCPProtocolError:
            # A cart write may already have succeeded. Preserve its returned ID
            # even if the server adds fields our detailed model cannot parse yet.
            cart_id = _string(payload, "cartId") if isinstance(payload, dict) else None
            if cart_id:
                return CartDetails(cartId=cart_id)
            raise

    async def get_cart(self, cart_id: str) -> CartDetails:
        """Return the current server-side cart, including its cartItemIds."""
        _require_identifier("cart_id", cart_id)
        payload = await self._call_tool(_GET_CART_TOOL, {"cartId": cart_id})
        cart = _parse_cart(payload, _GET_CART_TOOL)
        if cart.cart_id != cart_id:
            raise MCPProtocolError("getCart returned a cartId that does not match the request")
        return cart

    async def add_item_to_cart(
        self,
        cart_id: str,
        item_id: str,
        quantity: int = 1,
        *,
        options: list[CartOptionInput] | None = None,
        customer_note: str | None = None,
    ) -> CartDetails:
        """Add a catalog item; ``options`` is always sent, even when empty."""
        _require_identifier("cart_id", cart_id)
        item = CartItemInput(
            item_id=item_id,
            quantity=quantity,
            options=options or [],
            customer_note=customer_note,
        )
        payload = await self._call_tool(
            _ADD_CART_ITEM_TOOL,
            {"cartId": cart_id, **item.mcp_arguments()},
        )
        return _parse_matching_cart(payload, _ADD_CART_ITEM_TOOL, cart_id)

    async def update_cart_item(
        self,
        cart_id: str,
        cart_item_id: str,
        item_id: str,
        quantity: int,
        *,
        options: list[CartOptionInput] | None = None,
        customer_note: str | None = None,
    ) -> CartDetails:
        """Replace the complete state of an existing cart item."""
        _require_identifier("cart_id", cart_id)
        _require_identifier("cart_item_id", cart_item_id)
        item = CartItemInput(
            item_id=item_id,
            quantity=quantity,
            options=options or [],
            customer_note=customer_note,
        )
        payload = await self._call_tool(
            _UPDATE_CART_ITEM_TOOL,
            {
                "cartId": cart_id,
                "cartItemId": cart_item_id,
                **item.mcp_arguments(),
            },
        )
        return _parse_matching_cart(payload, _UPDATE_CART_ITEM_TOOL, cart_id)

    async def remove_item_from_cart(
        self,
        cart_id: str,
        cart_item_id: str,
    ) -> CartDetails | CartRemovalResult:
        """Remove by cartItemId, never by the catalog itemId."""
        _require_identifier("cart_id", cart_id)
        _require_identifier("cart_item_id", cart_item_id)
        payload = await self._call_tool(
            _REMOVE_CART_ITEM_TOOL,
            {"cartId": cart_id, "cartItemId": cart_item_id},
        )
        if not isinstance(payload, dict):
            raise MCPProtocolError("removeItemFromCart returned an invalid payload")
        if "cartId" not in payload:
            hints = payload.get("agentHints")
            if not isinstance(hints, dict) or "cartDeletedAfterLastItemRemoved" not in hints:
                raise MCPProtocolError("removeItemFromCart response is missing cartId")
            return CartRemovalResult.model_validate(payload)
        return _parse_matching_cart(payload, _REMOVE_CART_ITEM_TOOL, cart_id)

    async def submit_order(
        self,
        cart_id: str,
        *,
        confirmed: bool,
        document: str | None = None,
    ) -> CheckoutResult:
        """Forward checkout data and let ``submitOrder`` validate the cart."""
        _require_identifier("cart_id", cart_id)
        arguments: dict[str, Any] = {"cartId": cart_id, "userConsent": confirmed}
        if document is not None:
            if not document.strip():
                raise ValueError("document cannot be blank")
            arguments["document"] = document.strip()
        payload = await self._call_tool(_SUBMIT_ORDER_TOOL, arguments)
        if not isinstance(payload, dict):
            raise MCPProtocolError("ifood_submitOrder returned an invalid payload")
        return CheckoutResult.model_validate(payload)

    async def _resolve_user_location(
        self, address_id: str | None, latitude: float | None, longitude: float | None,
    ) -> dict[str, float]:
        if latitude is not None and longitude is not None:
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("userLocation coordinates are outside valid ranges")
            return {"latitude": latitude, "longitude": longitude}
        if address_id:
            addresses = await self.list_addresses()
            selected = next((item for item in addresses.addresses if item.address_id == address_id), None)
            if selected is None:
                raise ValueError("address_id was not returned by listAddresses")
            if selected.coordinates is None:
                raise ValueError("the selected iFood address has no coordinates")
            return {
                "latitude": selected.coordinates.latitude,
                "longitude": selected.coordinates.longitude,
            }
        raise ValueError("userLocation requires address_id or latitude and longitude")

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            payload = await self._client.call_tool(tool_name, arguments)
        except MCPToolError as exc:
            normalized_code = exc.code.upper()
            if normalized_code == "AUTHENTICATION_REQUIRED":
                raise MCPAuthenticationError(str(exc)) from exc
            if normalized_code in {"AUTHORIZATION_REQUIRED", "FORBIDDEN", "INSUFFICIENT_SCOPE"}:
                raise MCPAuthorizationError(str(exc)) from exc
            raise
        if isinstance(payload, dict):
            _raise_mcp_errors(payload)
        return payload

def _records(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [value for value in payload if isinstance(value, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records(value, keys)
            return nested or [value]
    return []


def _validate_offer_response(payload: Any, expected_kind: OfferResultKind) -> None:
    if not isinstance(payload, dict):
        raise MCPProtocolError("iFood Offer Discovery returned a non-object response")
    if payload.get("resultKind") != expected_kind.value:
        raise MCPProtocolError("iFood Offer Discovery returned an unexpected resultKind")
    if not isinstance(payload.get("results"), list) or not isinstance(payload.get("hasMore"), bool):
        raise MCPProtocolError("iFood Offer Discovery response is missing results or hasMore")


def _raise_mcp_errors(payload: dict[str, Any]) -> None:
    error = payload.get("error", payload.get("errors"))
    if not isinstance(error, dict):
        return
    code = str(error.get("code", "IFOOD_MCP_ERROR"))
    message = str(error.get("message", "iFood MCP operation failed"))
    normalized_code = code.upper()
    if normalized_code == "AUTHENTICATION_REQUIRED":
        raise MCPAuthenticationError(f"{code}: {message}")
    if normalized_code in {"AUTHORIZATION_REQUIRED", "FORBIDDEN", "INSUFFICIENT_SCOPE"}:
        raise MCPAuthorizationError(f"{code}: {message}")
    raise MCPToolError(code, message, payload)


def _require_identifier(name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


def _parse_cart(payload: Any, tool_name: str) -> CartDetails:
    if not isinstance(payload, dict):
        raise MCPProtocolError(f"{tool_name} returned an invalid payload")
    try:
        return CartDetails.model_validate(payload)
    except ValueError as exc:
        raise MCPProtocolError(f"{tool_name} returned an invalid cart") from exc


def _parse_matching_cart(payload: Any, tool_name: str, cart_id: str) -> CartDetails:
    cart = _parse_cart(payload, tool_name)
    if cart.cart_id != cart_id:
        raise MCPProtocolError(f"{tool_name} returned a cartId that does not match the request")
    return cart


def _string(value: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        candidate = value.get(key)
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        value = value.get("value", value.get("amount", value.get("current", value.get("price"))))
    if value is None:
        return None
    try:
        result = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def _details_to_product(details: ItemDetailsResult) -> ProductCandidate | None:
    if (
        details.availability is not AvailabilityStatus.available
        or details.price is None
        or details.name is None
        or details.merchant_id is None
    ):
        return None
    payload = details.data if isinstance(details.data, dict) else {}
    image = _string(payload, "itemImageUrl")
    package = _package_from_name(details.name)
    try:
        return ProductCandidate(
            id=details.item_id, merchant_id=details.merchant_id, name=details.name,
            description=_string(payload, "itemDescription"), price=details.price,
            currency="BRL", available=True,
            package_quantity=package[0] if package else None,
            package_unit=package[1] if package else None,
            image_url=image, source="ifood_mcp",
        )
    except ValueError:
        if image is None:
            return None
        return ProductCandidate(
            id=details.item_id, merchant_id=details.merchant_id, name=details.name,
            description=_string(payload, "itemDescription"), price=details.price,
            currency="BRL", available=True,
            package_quantity=package[0] if package else None,
            package_unit=package[1] if package else None,
            source="ifood_mcp",
        )


_PACKAGE = re.compile(r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|unidades?|unid(?:ades)?)\b", re.I)
_MULTIPACK = re.compile(r"(?<!\w)(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b", re.I)


def _package_from_name(name: str) -> tuple[Decimal, Unit] | None:
    """Read only an unambiguous quantity printed in the catalog item name."""
    multipack = list(_MULTIPACK.finditer(name))
    if multipack:
        if len(multipack) != 1 or len(_PACKAGE.findall(name)) != 1:
            return None
        count, amount, unit = multipack[0].groups()
        quantity = Decimal(count) * Decimal(amount.replace(",", "."))
    else:
        matches = list(_PACKAGE.finditer(name))
        if len(matches) != 1:
            return None
        amount, unit = matches[0].groups()
        quantity = Decimal(amount.replace(",", "."))
    if quantity <= 0:
        return None
    normalized = unit.casefold()
    if normalized.startswith(("un",)):
        return quantity, Unit.unit
    return quantity, Unit(normalized)
