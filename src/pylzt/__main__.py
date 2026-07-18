"""Demo CLI: `python -m pylzt demo-list <category> [--limit N]`.

Reads comma-separated market tokens from `LZT_TOKENS` and prints typed `Lot`
DTOs from the live API — proof the token-pooled read path works end to end.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from pylzt.client import Client
from pylzt.models.lot import LotFilter
from pylzt.types import Category


async def _demo_list(category: str, limit: int) -> int:
    raw = os.environ.get("LZT_TOKENS", "").strip()
    if not raw:
        print("LZT_TOKENS env var is empty — set comma-separated market tokens.", file=sys.stderr)
        return 2
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    client = Client(tokens)
    try:
        filter = LotFilter(category=Category.parse(category))
        lots = await client.market.list_lots(filter).collect(limit=limit)
        for lot in lots:
            print(f"{int(lot.item_id):>10}  {lot.price!s:>12} {lot.currency.value}  {lot.title}")
        print(f"\n{len(lots)} lots from category {category!r}")
        return 0
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pylzt")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo-list", help="print N lots from a category")
    demo.add_argument("category")
    demo.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)
    if args.command == "demo-list":
        return asyncio.run(_demo_list(args.category, args.limit))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
