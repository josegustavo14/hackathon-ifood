"""Run: python -m app.integrations.recipes.index_recipes PATH/TO/full_dataset.csv"""

from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from pathlib import Path

from app.integrations.recipes.recipenlg import build_index


def extract_csv(archive: Path) -> Path:
    """Extract only the dataset CSV beside a user-provided ZIP, without trusting ZIP paths."""
    with zipfile.ZipFile(archive) as source:
        members = [member for member in source.infolist()
                   if not member.is_dir() and Path(member.filename).name == "full_dataset.csv"]
        if len(members) != 1:
            raise ValueError("ZIP must contain exactly one full_dataset.csv")
        destination = archive.parent / "full_dataset.csv"
        temporary = archive.parent / "full_dataset.csv.extracting"
        try:
            with source.open(members[0]) as compressed, temporary.open("wb") as extracted:
                shutil.copyfileobj(compressed, extracted)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a locally downloaded RecipeNLG CSV")
    parser.add_argument("csv_path", type=Path, help="full_dataset.csv or a ZIP containing it")
    parser.add_argument("--index", type=Path, default=Path(".data/recipenlg.sqlite3"))
    args = parser.parse_args()
    csv_path = extract_csv(args.csv_path) if args.csv_path.suffix.casefold() == ".zip" else args.csv_path
    print(f"Indexed {build_index(csv_path, args.index)} recipes in {args.index}")


if __name__ == "__main__":
    main()
