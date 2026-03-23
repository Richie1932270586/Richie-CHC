from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.services.office_importer import OfficeImportService  # noqa: E402
from app.services.retriever import Retriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Office files into the local RAG knowledge base.")
    parser.add_argument("source_dir", help="Source folder path containing .docx/.xlsx/.pptx files")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep previously imported files for the same source folder instead of replacing them.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan the top level of the source folder.",
    )
    args = parser.parse_args()

    settings = get_settings()
    importer = OfficeImportService(settings, Retriever(settings))
    result = importer.import_folder(
        source_dir=args.source_dir,
        replace_existing=not args.keep_existing,
        recursive=not args.no_recursive,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
