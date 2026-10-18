"""End-to-end client for stdio and Streamable HTTP. Requires a running REST API."""

import argparse
import base64
from contextlib import asynccontextmanager
from datetime import timedelta
import json
from io import BytesIO
import os
from pathlib import Path
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def sample_meal_plan_pdf() -> bytes:
    """Small valid text PDF for exercising the actual meal plan parser."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject('/Type'): NameObject('/Font'),
        NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica'),
    })
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)}),
    })
    content = DecodedStreamObject()
    content.set_data(b'BT /F1 12 Tf 72 720 Td (Segunda) Tj 0 -20 Td (Cafe da manha: 40 g aveia) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@asynccontextmanager
async def connect(args):
    if args.url:
        async with streamablehttp_client(args.url) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=40)) as session:
                await session.initialize()
                yield session
    else:
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "app.mcp_server", "--api-url", args.api_url],
            cwd=Path(__file__).resolve().parents[2],
            env={"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=40)) as session:
                await session.initialize()
                yield session


async def check(args):
    async with connect(args) as session:
        async def call(name, **arguments):
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(f"{name}: {result.content}")
            data = result.structuredContent
            if data is None:
                raise RuntimeError(f"{name} não retornou dados estruturados")
            return data.get("result", data)

        tools = await session.list_tools()
        health = await call("health")
        # This smoke test only exercises the demonstrative flow, never commercial operations.
        if not health["mock_mode"]:
            raise RuntimeError("O smoke test exige MOCK_MODE=true no backend.")
        recipes = await call("search_recipes", query="lasanha")
        if not recipes:
            raise RuntimeError("A busca demonstrativa não retornou receitas")
        recipe = await call("get_recipe", recipe_id=recipes[0]["id"])
        nutrition = await call("calculate_nutrition", recipe_id=recipe["id"], servings=4)
        shopping = await call("calculate_shopping", recipe_id=recipe["id"], servings=4)
        matched = await call("match_products", shopping_list=shopping)
        proposal = await call("preview_cart", shopping_list=matched)
        rejected = await session.call_tool("apply_cart", {"proposal": proposal, "confirmed": False})
        if not rejected.isError:
            raise RuntimeError("Falha: aplicação sem autorização foi aceita")
        chat = await call("chat", message="Quero preparar lasanha")
        plan = await call("parse_meal_plan", filename="smoke.pdf", pdf_base64=base64.b64encode(sample_meal_plan_pdf()).decode())
        await session.read_resource("chef://guide")
        await session.get_prompt("prepare_recipe", {"dish": "lasanha", "servings": "4"})
        print(json.dumps({
            "ok": True, "transport": "streamable-http" if args.url else "stdio",
            "tools": len(tools.tools), "recipe": recipe["name"],
            "subtotal": proposal["estimated_subtotal"], "nutrition_status": nutrition["status"],
            "chat_status": chat["status"], "meal_plan_warnings": plan["extraction_warnings"],
            "confirmation_without_consent": "blocked", "cart_applied": False,
        }, ensure_ascii=True, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Testa o MCP Chef AI pelo protocolo real sem aplicar carrinho")
    parser.add_argument("--api-url", default=os.getenv("CHEF_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--url", help="Endpoint Streamable HTTP, por exemplo http://127.0.0.1:8001/mcp")
    args = parser.parse_args()
    try:
        anyio.run(check, args)
    except Exception as error:
        print(f"Smoke test falhou: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
