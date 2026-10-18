"""Validate PIX on an existing iFood cart and optionally submit it once.

The cart ID must be copied from the confirmed-cart result in the frontend. The
script never prints credentials, addresses, documents, or payment tokens.

From the repository root:
    backend/.venv/bin/python backend/tools/checkout_pix.py --cart-id <UUID>
    backend/.venv/bin/python backend/tools/checkout_pix.py --cart-id <UUID> --submit

``--submit`` is an explicit checkout action. It selects only a payment method
identified by iFood as PIX and calls ``submitOrder`` once; it never retries.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))
load_dotenv(REPOSITORY_ROOT / ".env")

from app.integrations.ifood import IFoodMCPGateway, oauth_token_store, refresh_access_token
from app.integrations.ifood.gateway import _find_pix_payment_method_id
from app.integrations.ifood.mcp import MCPError
from app.integrations.ifood.settings import IFoodMCPSettings


def latest_session_id() -> str | None:
    database_path = REPOSITORY_ROOT / "backend" / ".data" / "ifood_oauth.sqlite3"
    if not database_path.exists():
        return None
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT browser_session_id FROM oauth_tokens ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return str(row[0]) if row else None


async def access_token() -> str:
    session_id = latest_session_id()
    if session_id is None:
        raise RuntimeError("No local iFood OAuth session found. Connect through the frontend first.")
    tokens = oauth_token_store.get(session_id)
    if tokens is None:
        raise RuntimeError("The local iFood session is unavailable. Connect through the frontend again.")
    if oauth_token_store.refresh_required(session_id):
        if not tokens.refresh_token:
            raise RuntimeError("The iFood session expired. Connect through the frontend again.")
        tokens = await refresh_access_token(IFoodMCPSettings.from_environment(), tokens.refresh_token)
        oauth_token_store.put(session_id, tokens)
    return tokens.access_token


def _result_value(result, attribute: str) -> str | None:
    value = getattr(result, attribute, None)
    return value if isinstance(value, str) and value else None


async def run(cart_id: str, submit: bool) -> int:
    gateway = IFoodMCPGateway.from_environment(await access_token())
    try:
        cart = await gateway.get_cart(cart_id)
        merchant_id = cart.merchant.merchant_id if cart.merchant else None
        if not merchant_id:
            raise RuntimeError("The iFood cart did not return its merchant ID.")

        methods = await gateway._call_tool("listPaymentMethods", {"merchantId": merchant_id})
        pix_method_id = _find_pix_payment_method_id(methods)
        if pix_method_id is None:
            raise RuntimeError("iFood did not offer a selectable PIX method for this cart.")
        print("Cart: found")
        print("PIX: available")
        if not submit:
            print("Dry run only. Use --submit to select PIX and call checkout once.")
            return 0

        await gateway._call_tool("setCartPayment", {
            "cartId": cart_id,
            "paymentMethodId": pix_method_id,
        })
        print("PIX: selected")
        try:
            result = await gateway.submit_order(cart_id, confirmed=True)
        except MCPError as exc:
            print(f"Checkout failed: {exc}", file=sys.stderr)
            print("No retry was made.", file=sys.stderr)
            return 2

        print("Checkout: submitted")
        if value := _result_value(result, "order_id"):
            print(f"Order ID: {value}")
        if value := _result_value(result, "payment_url"):
            print(f"Payment URL: {value}")
        if value := _result_value(result, "pix_qr_code"):
            print(f"PIX QR/code: {value}")
        if not _result_value(result, "payment_url") and not _result_value(result, "pix_qr_code"):
            print("iFood submitted checkout but did not return a payment URL or PIX QR/code.")
        return 0
    finally:
        await gateway.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or submit an existing iFood cart using PIX.")
    parser.add_argument("--cart-id", required=True, help="UUID displayed after the cart was created.")
    parser.add_argument("--submit", action="store_true", help="Select PIX and submit checkout once.")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        raise SystemExit(asyncio.run(run(arguments.cart_id, arguments.submit)))
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
