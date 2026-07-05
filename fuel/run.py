"""CLI entrypoint for the fuel price scraper (Part C — first prototype).

Usage: `python -m fuel.run --source dgeg`
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from fuel.db import upsert_fuel_price
from fuel.dgeg import fetch_all_latest_prices


async def _main(source: str) -> int:
    load_dotenv()
    if source != "dgeg":
        print(f"Unknown fuel source {source!r}", file=sys.stderr)
        return 2

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    results = await fetch_all_latest_prices()

    if not results:
        print("WARNING: no fuel prices retrieved", file=sys.stderr)
        return 1

    for fuel_type, row in results.items():
        upsert_fuel_price(client, fuel_type, row)
        print(f"{fuel_type}: {row['date']} = {row['price']} {row['unit']}")

    # Missing fuel types (site down, selector drift) fail loudly so GitHub
    # Actions' native failure email is a backup signal — no scrape_runs/
    # Telegram integration yet for this first prototype.
    if len(results) < 3:
        missing = set(["gasoline_95", "diesel", "lpg_auto"]) - set(results)
        print(f"WARNING: missing fuel types: {missing}", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="dgeg", choices=["dgeg"])
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.source)))


if __name__ == "__main__":
    main()
