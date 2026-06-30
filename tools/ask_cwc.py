#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_cwc_index import INDEX_PATH
from tools.cwc_rag import format_cli_answer, query_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the local SHU finance office RAG index.")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    result = query_policy(" ".join(args.query), top_k=args.top_k, index_path=args.index)
    print(format_cli_answer(result))


if __name__ == "__main__":
    main()
