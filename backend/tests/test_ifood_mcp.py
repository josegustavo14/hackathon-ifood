import asyncio
import base64
import hashlib
import json
import sqlite3
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
from starlette.requests import Request

from app.core import dependencies
from app.integrations.ifood.gateway import IFoodMCPGateway, _find_pix_payment_method_id, _package_from_name
from app.integrations.ifood.cart import CartItemInput
from app.integrations.ifood.auth import (
    OAuthStateError,
    EncryptedSQLiteOAuthTokenStore,
    OAuthTokenStore,
    OAuthTokens,
    PKCEAuthorizationStore,
    create_pkce_authorization_request,
    exchange_authorization_code,
    refresh_access_token,
    revoke_token,
)
from app.integrations.ifood.mcp import MCPAuthorizationError, StreamableHTTPMCPClient
from app.integrations.ifood.models import MerchantType, OfferRefinements, OfferResultKind
from app.integrations.ifood.settings import IFoodMCPSettings
from app.integrations.ifood.shopping import IFoodShoppingEngine
from app.models.ingredient import Ingredient
from app.models.product import ProductCandidate
from app.models.shopping import ShoppingItem, ShoppingItemStatus, ShoppingList, ShoppingListStatus


def test_gateway_refreshes_expiring_oauth_session(monkeypatch):
    store = OAuthTokenStore()
    store.put("session", OAuthTokens(access_token="old", token_type="Bearer", expires_in=1, refresh_token="refresh"))
    config = settings()

    class SettingsFactory:
        @staticmethod
        def from_environment():
            return config

    class FakeGateway:
        def __init__(self, access_token):
            self.access_token = access_token
            self.closed = False

        async def aclose(self):
            self.closed = True

    async def fake_refresh(received_settings, refresh_token):
        assert received_settings is config
        assert refresh_token == "refresh"
        return OAuthTokens(access_token="new", token_type="Bearer", expires_in=3600, refresh_token="next")

    monkeypatch.setattr(dependencies, "get_settings", lambda: SimpleNamespace(mock_mode=False))
    monkeypatch.setattr(dependencies, "oauth_token_store", store)
    monkeypatch.setattr(dependencies, "IFoodMCPSettings", SettingsFactory)
    monkeypatch.setattr(dependencies, "refresh_access_token", fake_refresh)
    monkeypatch.setattr(dependencies.IFoodMCPGateway, "from_environment", lambda token: FakeGateway(token))
    request = Request({"type": "http", "headers": [(b"cookie", b"ifood_oauth_session=session")]})

    async def run():
        gateway_session = dependencies.get_ifood_gateway(request)
        gateway = await anext(gateway_session)
        assert gateway.access_token == "new"
        assert store.get("session").access_token == "new"
        await gateway_session.aclose()
        assert gateway.closed

    asyncio.run(run())


def settings() -> IFoodMCPSettings:
    return IFoodMCPSettings(
        mcp_url="https://mcp.example.test/mcp",
        authorize_url="https://auth.example.test/authorize",
        redirect_uri="http://localhost:8000/api/v1/ifood/oauth/callback", client_id="client-1", client_secret="secret-1",
        token_url="https://auth.example.test/token", revoke_url="https://auth.example.test/revoke",
        access_token="local-token", scope=None,
        timeout_seconds=1, session_cookie_max_age_seconds=3600,
    )


def test_mcp_initializes_then_uses_bearer_token_and_session():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return httpx.Response(200, headers={"Mcp-Session-Id": "session-1"}, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"structuredContent": {"products": []}}})

    async def run() -> None:
        client = StreamableHTTPMCPClient(settings(), transport=httpx.MockTransport(handler))
        assert await client.call_tool("ifood_searchOffers", {"query": "leite"}) == {"products": []}
        await client.aclose()

    asyncio.run(run())
    assert [json.loads(request.content)["method"] for request in requests] == ["initialize", "notifications/initialized", "tools/call"]
    assert requests[0].headers["authorization"] == "Bearer local-token"
    assert requests[-1].headers["mcp-session-id"] == "session-1"


def test_gateway_maps_prices_and_product_availability():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            if name == "searchOffers":
                assert arguments == {
                    "query": "leite", "resultKind": "ITEM",
                    "userLocation": {"latitude": -12.97, "longitude": -38.50},
                    "pageSize": 10, "merchantType": "GROCERIES",
                    "refinements": {"merchantId": "market-1"},
                }
                return {"resultKind": "ITEM", "results": [{
                    "itemId": "milk-1", "itemName": "Leite integral 1L", "unitPrice": 6.90,
                    "promotionalUnitPrice": 5.90,
                    "merchant": {"merchantId": "market-1", "merchantName": "Mercado"},
                }], "hasMore": False}
            raise AssertionError("search_products must not fetch every item detail")

        async def aclose(self):
            pass

    async def run():
        return await IFoodMCPGateway(settings(), FakeMCP()).search_products(
            "leite", "market-1", latitude=-12.97, longitude=-38.50,
        )

    products = asyncio.run(run())
    assert len(products) == 1
    assert products[0].price == Decimal("5.90")
    assert products[0].available is True
    assert products[0].package_unit.value == "l"
    assert products[0].package_quantity == Decimal("1")


def test_package_size_is_read_only_from_unambiguous_catalog_name():
    assert _package_from_name("Macarrão Espaguete 500g") == (Decimal("500"), "g")
    assert _package_from_name("Leite integral 1L") == (Decimal("1"), "l")
    assert _package_from_name("Iogurte 4 x 170g") == (Decimal("680"), "g")
    assert _package_from_name("Queijo 200g + 50g grátis") is None
    assert _package_from_name("Leite integral") is None


def test_cart_gateway_uses_live_mcp_tool_names_without_network():
    calls = []

    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            calls.append((name, arguments))
            return {"cartId": "cart-1", "items": [{"newServerField": True}]} if name == "createCart" else {"cartId": "cart-1"}

        async def aclose(self):
            pass

    async def run():
        gateway = IFoodMCPGateway(settings(), FakeMCP())
        created = await gateway.create_cart("merchant-1", "address-1", [CartItemInput(itemId="item-1", quantity=2)])
        fetched = await gateway.get_cart(created.cart_id)
        return created, fetched

    created, fetched = asyncio.run(run())
    assert created.cart_id == fetched.cart_id == "cart-1"
    assert calls == [
        ("createCart", {"merchantId": "merchant-1", "addressId": "address-1", "items": [
            {"itemId": "item-1", "quantity": 2, "options": []}]}),
        ("getCart", {"cartId": "cart-1"}),
    ]


def test_gateway_selects_only_a_server_issued_pix_method():
    pix_id = "f0f6b0d4-7c43-4bb5-a7b0-fc205e2dd8d2"
    calls = []

    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            calls.append((name, arguments))
            if name == "getCart":
                return {"cartId": "cart-1", "paymentMethods": [
                    {"paymentMethodId": pix_id, "name": "PIX"},
                    {"paymentMethodId": "not-a-uuid", "name": "PIX inválido"},
                ]}
            assert name == "setCartPayment"
            return {"cartId": "cart-1"}

        async def aclose(self):
            pass

    assert asyncio.run(IFoodMCPGateway(settings(), FakeMCP()).select_pix_payment("cart-1")) is True
    assert calls == [
        ("getCart", {"cartId": "cart-1"}),
        ("setCartPayment", {"cartId": "cart-1", "paymentMethodId": pix_id}),
    ]
    assert _find_pix_payment_method_id({"name": "PIX", "paymentMethodId": "PIX"}) is None
    assert _find_pix_payment_method_id({"kind": "PIX", "paymentMethodId": pix_id}) == pix_id


def test_gateway_reads_payment_methods_when_cart_omits_them():
    pix_id = "f0f6b0d4-7c43-4bb5-a7b0-fc205e2dd8d2"
    calls = []

    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            calls.append((name, arguments))
            if name == "getCart":
                return {"cartId": "cart-1"}
            if name == "listPaymentMethods":
                return {"paymentMethods": [{"paymentMethodId": pix_id, "kind": "PIX"}]}
            return {"cartId": "cart-1"}

        async def aclose(self):
            pass

    assert asyncio.run(IFoodMCPGateway(settings(), FakeMCP()).select_pix_payment("cart-1", "merchant-1")) is True
    assert calls == [
        ("getCart", {"cartId": "cart-1"}),
        ("listPaymentMethods", {"merchantId": "merchant-1"}),
        ("setCartPayment", {"cartId": "cart-1", "paymentMethodId": pix_id}),
    ]


def test_gateway_keeps_checkout_pix_payload_when_ifood_returns_it():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            assert name == "submitOrder"
            assert arguments == {"cartId": "cart-1", "userConsent": True}
            return {
                "cartId": "cart-1", "orderId": "order-1",
                "paymentUrl": "https://payments.example.test/pix/order-1",
                "pixQrCode": "000201010212...",
            }

        async def aclose(self):
            pass

    result = asyncio.run(IFoodMCPGateway(settings(), FakeMCP()).submit_order("cart-1", confirmed=True))
    assert result.order_id == "order-1"
    assert result.payment_url == "https://payments.example.test/pix/order-1"
    assert result.pix_qr_code == "000201010212..."


def test_gateway_lists_documented_delivery_addresses_before_discovery():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            assert name == "listAddresses"
            assert arguments == {}
            return {
                "results": [{
                    "addressId": "address-1", "formattedAddress": "Rua A, 10, Salvador, BA",
                    "alias": "Casa", "coordinates": {"latitude": -12.97, "longitude": -38.50},
                    "isLastUsedAddress": True,
                }],
                "agentHints": {"addressCount": 1},
            }

        async def aclose(self):
            pass

    async def run():
        gateway = IFoodMCPGateway(settings(), FakeMCP())
        return await gateway.list_addresses()

    result = asyncio.run(run())
    assert result.addresses[0].address_id == "address-1"
    assert result.addresses[0].coordinates.latitude == -12.97
    assert result.agent_hints["addressCount"] == 1


def test_browse_offers_uses_nested_location_and_documented_refinements():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            assert name == "browseOffers"
            assert arguments == {
                "merchantType": "GROCERIES", "resultKind": "ITEM",
                "userLocation": {"latitude": -12.97, "longitude": -38.50},
                "pageSize": 25, "nextPageToken": "opaque-token",
                "refinements": {
                    "itemTaxonomy": ["dairy"], "merchantId": "market-1",
                    "maxItemPrice": 20.0, "onlyOpen": True, "sort": "PRICE",
                },
            }
            return {"resultKind": "ITEM", "merchantType": "GROCERIES", "results": [], "hasMore": False}

        async def aclose(self):
            pass

    async def run():
        gateway = IFoodMCPGateway(settings(), FakeMCP())
        return await gateway.browse_offers(
            merchant_type=MerchantType.GROCERIES, result_kind=OfferResultKind.ITEM,
            latitude=-12.97, longitude=-38.50, page_size=25,
            next_page_token="opaque-token",
            refinements=OfferRefinements(
                item_taxonomy=["dairy"], merchant_id="market-1",
                max_item_price="20.00", only_open=True, sort="PRICE",
            ),
        )

    assert asyncio.run(run()).data["resultKind"] == "ITEM"


def test_saved_address_is_resolved_to_documented_user_location():
    calls: list[str] = []

    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            calls.append(name)
            if name == "listAddresses":
                return {"results": [{
                    "addressId": "address-1", "formattedAddress": "Rua A, 10",
                    "coordinates": {"latitude": -12.97, "longitude": -38.50},
                }]}
            assert arguments["userLocation"] == {"latitude": -12.97, "longitude": -38.50}
            return {"resultKind": "MERCHANT", "results": [], "hasMore": False}

        async def aclose(self):
            pass

    async def run():
        return await IFoodMCPGateway(settings(), FakeMCP()).search_offers("mercado", address_id="address-1")

    asyncio.run(run())
    assert calls == ["listAddresses", "searchOffers"]


def test_merchant_details_include_location_and_operational_fields():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            assert name == "getMerchant"
            assert arguments == {
                "merchantId": "market-1",
                "userLocation": {"latitude": -12.97, "longitude": -38.50},
            }
            return {
                "merchantId": "market-1", "merchantName": "Mercado do Bairro",
                "merchantType": "GROCERIES", "isOpen": True,
                "minimumOrderAmount": 15.00, "featuredItems": [],
            }

        async def aclose(self):
            pass

    async def run():
        return await IFoodMCPGateway(settings(), FakeMCP()).get_merchant(
            "market-1", latitude=-12.97, longitude=-38.50,
        )

    result = asyncio.run(run())
    assert result.name == "Mercado do Bairro"
    assert result.merchant_type == "GROCERIES"
    assert result.is_open is True
    assert result.minimum_order_amount == Decimal("15.00")


def test_item_details_use_promotional_price_and_confirm_current_availability():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            assert name == "getItem"
            assert arguments == {
                "itemId": "milk-1", "merchantId": "market-1",
                "userLocation": {"latitude": -12.97, "longitude": -38.50},
            }
            return {
                "itemId": "milk-1", "merchantId": "market-1", "itemName": "Leite integral",
                "unitPrice": 6.90, "promotionalUnitPrice": 5.90, "optionGroups": [],
            }

        async def aclose(self):
            pass

    async def run():
        gateway = IFoodMCPGateway(settings(), FakeMCP())
        return await gateway.get_item("milk-1", "market-1", latitude=-12.97, longitude=-38.50)

    result = asyncio.run(run())
    assert result.unit_price == Decimal("6.90")
    assert result.promotional_unit_price == Decimal("5.90")
    assert result.price == Decimal("5.90")
    assert result.availability == "available"


def test_mcp_server_is_the_authority_for_oauth_permissions():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async def run():
        client = StreamableHTTPMCPClient(settings(), transport=httpx.MockTransport(handler))
        try:
            await client.list_tools()
        finally:
            await client.aclose()

    try:
        asyncio.run(run())
    except MCPAuthorizationError:
        pass
    else:
        raise AssertionError("HTTP 403 from iFood must be preserved as an authorization denial")


def test_item_not_found_is_reported_as_unavailable():
    class FakeMCP:
        async def call_tool(self, name: str, arguments: dict):
            return {"errors": {
                "code": "ITEM_NOT_FOUND", "message": "Item was removed from the menu",
                "mcpCode": -32301, "retryable": False,
            }}

        async def aclose(self):
            pass

    async def run():
        return await IFoodMCPGateway(settings(), FakeMCP()).get_item(
            "milk-1", "market-1", latitude=-12.97, longitude=-38.50,
        )

    result = asyncio.run(run())
    assert result.availability == "unavailable"
    assert result.price is None


def test_live_matching_marks_out_of_stock_products_unavailable():
    ingredient = Ingredient(id="milk", name="Leite", quantity="2", unit="l")
    product = ProductCandidate(
        id="milk-1", merchant_id="market-1", name="Leite", price="6.90",
        package_quantity="1", package_unit="l", available=False, source="ifood_mcp",
    )
    shopping_list = ShoppingList(
        id="list-1", items=[ShoppingItem(ingredient=ingredient, purchase_quantity=0, total_price="0.00", status="pending")],
        estimated_subtotal="0.00", unresolved_ingredients=[ingredient], status=ShoppingListStatus.pending,
    )
    result = IFoodShoppingEngine().match_products(shopping_list, [product])
    assert result.items[0].status is ShoppingItemStatus.unavailable
    assert result.estimated_subtotal == Decimal("0.00")


def test_pkce_authorization_request_uses_s256_without_leaking_verifier():
    request = create_pkce_authorization_request(settings())
    challenge = base64.urlsafe_b64encode(hashlib.sha256(request.code_verifier.encode()).digest()).rstrip(b"=").decode()
    assert request.state in request.authorization_url
    assert f"code_challenge={challenge}" in request.authorization_url
    assert "code_challenge_method=S256" in request.authorization_url
    assert request.code_verifier not in request.authorization_url


def test_callback_state_must_match_its_browser_session_and_is_single_use():
    store = PKCEAuthorizationStore()
    request = store.begin(settings(), "browser-session")
    verifier = store.consume_callback(request.state, "browser-session")
    assert verifier == request.code_verifier
    try:
        store.consume_callback(request.state, "browser-session")
    except OAuthStateError:
        pass
    else:
        raise AssertionError("OAuth state must be single use")


def test_authorization_code_exchange_keeps_tokens_server_side():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "access_token": "access", "id_token": "identity", "refresh_token": "refresh",
            "token_type": "Bearer", "expires_in": 3600,
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await exchange_authorization_code(settings(), "authorization-code", "verifier", client=client)

    tokens = asyncio.run(run())
    body = requests[0].content.decode()
    assert tokens.access_token == "access"
    assert "grant_type=authorization_code" in body
    assert "code_verifier=verifier" in body
    assert "client_secret" in body


def test_refresh_token_exchange_rotates_the_token_pair():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "access_token": "new-access", "id_token": "new-identity", "refresh_token": "new-refresh",
            "token_type": "Bearer", "expires_in": 3600,
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await refresh_access_token(settings(), "old-refresh", client=client)

    tokens = asyncio.run(run())
    body = requests[0].content.decode()
    assert tokens.access_token == "new-access"
    assert tokens.refresh_token == "new-refresh"
    assert "grant_type=refresh_token" in body
    assert "refresh_token=old-refresh" in body
    assert "code_verifier" not in body


def test_revoke_prefers_a_backend_form_request():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await revoke_token(settings(), "refresh-to-revoke", client=client)

    asyncio.run(run())
    body = requests[0].content.decode()
    assert requests[0].url == "https://auth.example.test/revoke"
    assert "token=refresh-to-revoke" in body
    assert "client_id=client-1" in body
    assert "client_secret=secret-1" in body


def test_refresh_uses_a_five_minute_expiry_buffer():
    store = OAuthTokenStore()
    store.put("session", OAuthTokens(
        access_token="access", refresh_token="refresh", token_type="Bearer", expires_in=299,
    ))
    assert store.refresh_required("session") is True


def test_encrypted_token_store_survives_restart_without_plaintext(tmp_path):
    database_path = tmp_path / "oauth.sqlite3"
    tokens = OAuthTokens(
        access_token="access-secret", refresh_token="refresh-secret",
        id_token="identity-secret", token_type="Bearer", expires_in=3600,
        granted_scopes=frozenset({"mcp.discovery.search.read"}),
    )

    first_process = EncryptedSQLiteOAuthTokenStore(database_path, "encryption-secret")
    first_process.put("browser-session", tokens)

    database_bytes = database_path.read_bytes()
    assert b"access-secret" not in database_bytes
    assert b"refresh-secret" not in database_bytes
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM oauth_tokens").fetchone()[0] == 1

    restarted_process = EncryptedSQLiteOAuthTokenStore(database_path, "encryption-secret")
    assert restarted_process.get("browser-session") == tokens
    assert restarted_process.refresh_required("browser-session") is False

    restarted_process.delete("browser-session")
    assert first_process.get("browser-session") is None


def test_encrypted_token_store_invalidates_session_after_key_rotation(tmp_path):
    database_path = tmp_path / "oauth.sqlite3"
    original = EncryptedSQLiteOAuthTokenStore(database_path, "original-secret")
    original.put("browser-session", OAuthTokens(
        access_token="access", refresh_token="refresh",
        token_type="Bearer", expires_in=3600,
    ))

    rotated = EncryptedSQLiteOAuthTokenStore(database_path, "rotated-secret")
    assert rotated.get("browser-session") is None
    assert original.get("browser-session") is None


def test_production_urls_require_https_but_localhost_may_use_http():
    settings().validate_authorization()
    insecure = replace(settings(), authorize_url="http://auth.example.test/authorize")
    try:
        insecure.validate_authorization()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Non-local OAuth URLs must use HTTPS")
