from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.contracts import IFoodGateway
from app.core.dependencies import get_ifood_gateway
from app.integrations.ifood.mcp import MCPAuthenticationError, MCPAuthorizationError, MCPError
from app.integrations.ifood.models import (
    AddressListResponse,
    BrowseOffersRequest,
    ItemDetailsResult,
    MCPToolResult,
    MerchantDetailsResult,
    OfferLocationRequest,
    SearchOffersRequest,
)
from app.integrations.ifood.settings import IFoodConfigurationError

router = APIRouter(prefix="/ifood", tags=["ifood"])


@router.get("/addresses", response_model=AddressListResponse)
async def list_addresses(
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
) -> AddressListResponse:
    try:
        return await gateway.list_addresses()
    except IFoodConfigurationError as exc:
        raise HTTPException(status_code=503, detail="iFood consumer MCP is not configured") from exc
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/mcp/tools", response_model=list[dict[str, Any]])
async def list_mcp_tools(
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
) -> list[dict[str, Any]]:
    """Inspect the tools and JSON schemas exposed to the current OAuth token."""
    try:
        return await gateway.list_tools()
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/offers/search", response_model=MCPToolResult)
async def search_offers(
    request: SearchOffersRequest,
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
) -> MCPToolResult:
    try:
        return await gateway.search_offers(
            request.query,
            merchant_type=request.merchant_type,
            result_kind=request.result_kind,
            refinements=request.refinements,
            page_size=request.page_size,
            next_page_token=request.next_page_token,
            address_id=request.address_id,
            latitude=request.latitude,
            longitude=request.longitude,
        )
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/offers/browse", response_model=MCPToolResult)
async def browse_offers(
    request: BrowseOffersRequest,
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
) -> MCPToolResult:
    try:
        return await gateway.browse_offers(
            merchant_type=request.merchant_type,
            result_kind=request.result_kind,
            refinements=request.refinements,
            page_size=request.page_size,
            next_page_token=request.next_page_token,
            address_id=request.address_id,
            latitude=request.latitude,
            longitude=request.longitude,
        )
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/items/{item_id}", response_model=ItemDetailsResult)
async def get_item(
    item_id: str,
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
    merchant_id: str,
    address_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ItemDetailsResult:
    try:
        location = OfferLocationRequest(address_id=address_id, latitude=latitude, longitude=longitude)
        return await gateway.get_item(
            item_id, merchant_id, address_id=location.address_id,
            latitude=location.latitude, longitude=location.longitude,
        )
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/merchants/{merchant_id}", response_model=MerchantDetailsResult)
async def get_merchant(
    merchant_id: str,
    gateway: Annotated[IFoodGateway, Depends(get_ifood_gateway)],
    address_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> MerchantDetailsResult:
    try:
        location = OfferLocationRequest(address_id=address_id, latitude=latitude, longitude=longitude)
        return await gateway.get_merchant(
            merchant_id, address_id=location.address_id,
            latitude=location.latitude, longitude=location.longitude,
        )
    except MCPAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="iFood session expired; reconnect your account") from exc
    except MCPAuthorizationError as exc:
        raise HTTPException(status_code=403, detail="iFood denied this operation for the current OAuth token") from exc
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
