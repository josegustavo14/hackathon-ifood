import argparse
import logging
import os
import sys

from .client import ChefAPI
from .server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP local para a API iFood Chef AI")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--api-url", default=os.getenv("CHEF_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--port", type=int, default=8001, help="Porta HTTP local; não usada em stdio")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1 e 65535")
    try:
        api = ChefAPI(args.api_url)
    except ValueError as error:
        parser.error(str(error))
    # stdout is exclusively for JSON-RPC when using stdio.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    create_server(api, port=args.port).run(transport=args.transport)


if __name__ == "__main__":
    main()
