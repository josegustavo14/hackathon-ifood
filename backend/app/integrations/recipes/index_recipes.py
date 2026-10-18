"""Run: python -m app.integrations.recipes.index_recipes PATH/TO/full_dataset.csv"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.integrations.recipes.recipenlg import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a locally downloaded RecipeNLG CSV")
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--index", type=Path, default=Path(".data/recipenlg.sqlite3"))
    args = parser.parse_args()
    print(f"Indexed {build_index(args.csv_path, args.index)} recipes in {args.index}")


if __name__ == "__main__":
    main()
