"""Typed boundary models for the documented iFood consumer MCP responses."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.common import Money


class IFoodModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Coordinates(IFoodModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class AddressLocation(IFoodModel):
    street: str | None = None
    number: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None


class DeliveryAddress(IFoodModel):
    address_id: str = Field(validation_alias="addressId")
    formatted_address: str = Field(validation_alias="formattedAddress")
    alias: str | None = None
    location: AddressLocation | None = None
    postal_code: str | None = Field(default=None, validation_alias="postalCode")
    complement: str | None = None
    reference: str | None = None
    coordinates: Coordinates | None = None
    is_last_used_address: bool = Field(default=False, validation_alias="isLastUsedAddress")
    is_most_used_address_30d: bool = Field(default=False, validation_alias="isMostUsedAddress30d")
    top_merchant_types: dict[str, str] = Field(default_factory=dict, validation_alias="topMerchantTypes")
    top_week_day_shift: dict[str, str] = Field(default_factory=dict, validation_alias="topWeekDayShift")
    orders_by_merchant_type_weekday_and_shift: dict[str, dict[str, dict[str, str]]] = Field(
        default_factory=dict, validation_alias="ordersByMerchantTypeWeekdayAndShift"
    )


class AddressListResponse(IFoodModel):
    addresses: list[DeliveryAddress]
    agent_hints: dict[str, object] = Field(default_factory=dict)


class MerchantType(StrEnum):
    RESTAURANT = "RESTAURANT"
    GROCERIES = "GROCERIES"
    LIQUORSTORE = "LIQUORSTORE"
    DRUGSTORE = "DRUGSTORE"
    PETSTORE = "PETSTORE"
    SHOPPING = "SHOPPING"


class OfferResultKind(StrEnum):
    MERCHANT = "MERCHANT"
    ITEM = "ITEM"


class OfferSort(StrEnum):
    RELEVANCE = "RELEVANCE"
    PRICE = "PRICE"
    DELIVERY_TIME = "DELIVERY_TIME"


class RequiredDeliveryMethod(StrEnum):
    DELIVERY = "DELIVERY"
    TAKEOUT = "TAKEOUT"
    ANY = "ANY"


class DietaryFilter(StrEnum):
    VEGETARIAN = "VEGETARIAN"
    VEGAN = "VEGAN"
    GLUTEN_FREE = "GLUTEN_FREE"


class OfferRefinements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_taxonomy: list[str] | None = None
    merchant_id: str | None = Field(default=None, min_length=1)
    max_item_price: Money | None = None
    min_item_price: Money | None = None
    max_delivery_fee: Money | None = None
    max_distance_km: float | None = Field(default=None, gt=0)
    max_delivery_time_minutes: int | None = Field(default=None, gt=0)
    only_open: bool | None = None
    sort: OfferSort | None = None
    dietary: list[DietaryFilter] | None = None
    required_delivery_method: RequiredDeliveryMethod | None = None

    @model_validator(mode="after")
    def validate_price_range(self):
        if (
            self.min_item_price is not None
            and self.max_item_price is not None
            and self.min_item_price > self.max_item_price
        ):
            raise ValueError("min_item_price cannot be greater than max_item_price")
        return self

    def mcp_arguments(self, *, browse: bool = False) -> dict[str, Any]:
        mapping = {
            "itemTaxonomy": self.item_taxonomy,
            "merchantId": self.merchant_id,
            "maxItemPrice": float(self.max_item_price) if self.max_item_price is not None else None,
            "minItemPrice": float(self.min_item_price) if self.min_item_price is not None and not browse else None,
            "maxDeliveryFee": float(self.max_delivery_fee) if self.max_delivery_fee is not None else None,
            "maxDistanceKm": self.max_distance_km,
            "maxDeliveryTimeMinutes": self.max_delivery_time_minutes,
            "onlyOpen": self.only_open,
            "sort": self.sort.value if self.sort else None,
            "dietary": [value.value for value in self.dietary] if self.dietary else None,
            "requiredDeliveryMethod": (
                self.required_delivery_method.value if not browse and self.required_delivery_method else None
            ),
        }
        return {key: value for key, value in mapping.items() if value is not None}


class OfferLocationRequest(BaseModel):
    """Location accepted by Offer Discovery.

    A saved ``address_id`` is preferred. Coordinates are supported for the
    documented fallback where the address service is unavailable.
    """

    model_config = ConfigDict(extra="forbid")

    address_id: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_location(self):
        coordinates_complete = self.latitude is not None and self.longitude is not None
        coordinates_partial = (self.latitude is None) != (self.longitude is None)
        if coordinates_partial:
            raise ValueError("latitude and longitude must be provided together")
        if not self.address_id and not coordinates_complete:
            raise ValueError("provide address_id or latitude and longitude")
        if self.address_id and coordinates_complete:
            raise ValueError("provide address_id or coordinates, not both")
        return self

class SearchOffersRequest(OfferLocationRequest):
    query: str = Field(min_length=1)
    result_kind: OfferResultKind = OfferResultKind.MERCHANT
    merchant_type: MerchantType | None = None
    refinements: OfferRefinements | None = None
    page_size: int = Field(default=10, ge=1, le=25)
    next_page_token: str | None = Field(default=None, min_length=1)


class BrowseOffersRequest(OfferLocationRequest):
    merchant_type: MerchantType
    result_kind: OfferResultKind = OfferResultKind.MERCHANT
    refinements: OfferRefinements | None = None
    page_size: int = Field(default=10, ge=1, le=25)
    next_page_token: str | None = Field(default=None, min_length=1)


class MCPToolResult(IFoodModel):
    tool: str
    data: Any


class AvailabilityStatus(StrEnum):
    available = "available"
    unavailable = "unavailable"
    unknown = "unknown"


class ItemDetailsResult(MCPToolResult):
    item_id: str
    merchant_id: str | None = None
    name: str | None = None
    price: Money | None = None  # Effective price (promotional when active).
    unit_price: Money | None = None
    promotional_unit_price: Money | None = None
    currency: str = "BRL"
    availability: AvailabilityStatus


class MerchantDetailsResult(MCPToolResult):
    merchant_id: str
    name: str | None = None
    merchant_type: MerchantType | None = None
    is_open: bool | None = None
    minimum_order_amount: Money | None = None
