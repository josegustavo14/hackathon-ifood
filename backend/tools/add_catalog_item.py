"""Add one catalog product to an iFood cart using the local OAuth session.

Run from the repository root:
    backend/.venv/bin/python backend/tools/add_catalog_item.py --query "molho de tomate" --apply

The script never prints OAuth tokens and never calls checkout or payment tools.
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

from app.integrations.ifood import CartItemInput, IFoodMCPGateway, oauth_token_store, refresh_access_token
from app.integrations.ifood.models import MerchantType, OfferResultKind
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
        refreshed = await refresh_access_token(IFoodMCPSettings.from_environment(), tokens.refresh_token)
        oauth_token_store.put(session_id, refreshed)
        tokens = refreshed
    return tokens.access_token


async def run(query: str, quantity: int, apply: bool) -> int:
    gateway = IFoodMCPGateway.from_environment(await access_token())
    try:
        addresses = await gateway.list_addresses()
        address = next(
            (item for item in addresses.addresses if item.is_last_used_address),
            addresses.addresses[0] if addresses.addresses else None,
        )
        if address is None or address.coordinates is None:
            raise RuntimeError("No saved iFood delivery address with coordinates was found.")

        offers = await gateway.search_offers(
            query,
            merchant_type=MerchantType.GROCERIES,
            result_kind=OfferResultKind.ITEM,
            latitude=address.coordinates.latitude,
            longitude=address.coordinates.longitude,
            page_size=10,
        )
        raw_items = offers.data.get("results", [])
        if not raw_items:
            raise RuntimeError(f"No catalog item was found for: {query}")

        chosen = raw_items[0]
        merchant = chosen.get("merchant") if isinstance(chosen.get("merchant"), dict) else {}
        item_id = chosen.get("itemId")
        merchant_id = merchant.get("merchantId") or chosen.get("merchantId")
        if not isinstance(item_id, str) or not isinstance(merchant_id, str):
            raise RuntimeError("The catalog response did not include a valid product and merchant ID.")

        details = await gateway.get_item(
            item_id,
            merchant_id,
            latitude=address.coordinates.latitude,
            longitude=address.coordinates.longitude,
        )
        print(f"Product: {details.name}")
        print(f"Unit price: R$ {details.price:.2f}" if details.price is not None else "Unit price: unavailable")
        print(f"Quantity: {quantity}")
        print(f"Merchant: {merchant.get('merchantName') or merchant_id}")

        if not apply:
            print("Dry run only. Re-run with --apply to create an iFood cart.")
            return 0

        cart = await gateway.create_cart(
            merchant_id,
            address.address_id,
            [CartItemInput(itemId=item_id, quantity=quantity)],
        )
        pix_selected = await gateway.select_pix_payment(cart.cart_id)
        print("Result: item added to an iFood cart")
        print(f"Cart ID: {cart.cart_id}")
        print("PIX: selected" if pix_selected else "PIX: no selectable method was returned by iFood")
        if cart.app_deeplink:
            print(f"Cart link: {cart.app_deeplink}")
        print("Checkout and payment were not requested.")
        return 0
    finally:
        await gateway.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add a searched iFood grocery item to a cart.")
    parser.add_argument("--query", default="molho de tomate", help="Product query sent to the iFood catalog.")
    parser.add_argument("--quantity", type=int, default=1, choices=range(1, 100), metavar="1-99")
    parser.add_argument("--apply", action="store_true", help="Create the cart. Omit for a read-only dry run.")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        raise SystemExit(asyncio.run(run(arguments.query, arguments.quantity, arguments.apply)))
    except Exception as error:  # CLI boundary: show an actionable log without secrets.
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1)
