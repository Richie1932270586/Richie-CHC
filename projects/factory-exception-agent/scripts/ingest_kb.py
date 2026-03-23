from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "api"))

from app.core.config import get_settings  # noqa: E402
from app.services.retriever import build_kb_index  # noqa: E402


def main() -> None:
    settings = get_settings()
    index_payload = build_kb_index(settings)
    print(f"Indexed documents: {len(index_payload.get('documents', []))}")
    print(f"Indexed chunks: {len(index_payload.get('chunks', []))}")
    print(f"Index file: {settings.index_file}")


if __name__ == "__main__":
    main()
