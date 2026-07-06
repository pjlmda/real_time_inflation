"""CLI entrypoint for the fuel price scraper (Part C — first prototype).

Usage: `python -m fuel.run --source dgeg`

Alerts via the same Telegram notifier as the grocery scrapers on total
failure or a missing fuel type. There's no `scrape_runs` table for fuel
(no per-run `alerted` dedup) — this is a single daily run per fuel type,
so an unconditional send on failure is simple enough for this prototype.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from alerting.base import Notifier
from alerting.console import ConsoleNotifier
from alerting.telegram import TelegramNotifier
from fuel.db import upsert_fuel_price
from fuel.dgeg import fetch_all_latest_prices

ALL_FUEL_TYPES = {"gasoline_95", "diesel", "lpg_auto"}


def _build_notifier() -> Notifier:
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return TelegramNotifier(token=token, chat_id=chat_id)
    print(
        "WARNING: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set — alerts will only "
        "print to the console, not reach Telegram.",
        file=sys.stderr,
    )
    return ConsoleNotifier()


async def _main(source: str) -> int:
    load_dotenv()
    if source != "dgeg":
        print(f"Unknown fuel source {source!r}", file=sys.stderr)
        return 2

    notifier = _build_notifier()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    results = await fetch_all_latest_prices()

    if not results:
        await notifier.send("*Fuel scrape failed* (dgeg)\nNo fuel prices retrieved at all.")
        print("WARNING: no fuel prices retrieved", file=sys.stderr)
        return 1

    write_errors: list[str] = []
    for fuel_type, row in results.items():
        try:
            upsert_fuel_price(client, fuel_type, row)
            print(f"{fuel_type}: {row['date']} = {row['price']} {row['unit']}")
        except Exception as exc:  # noqa: BLE001 - one fuel type's DB write failing shouldn't
            # skip the rest, or crash before this reaches Telegram the way an uncaught
            # exception would.
            write_errors.append(f"{fuel_type}: {exc}")
            print(f"WARNING: failed to write {fuel_type} to Supabase: {exc}", file=sys.stderr)

    # Missing fuel types (site down, selector drift) or a DB write failure both
    # alert via Telegram, same as the grocery scrapers' coverage-below-threshold
    # alert (spec §8) — no scrape_runs table for fuel yet, so there's no
    # `alerted` dedup here.
    missing = ALL_FUEL_TYPES - set(results)
    if missing or write_errors:
        lines = []
        if missing:
            lines.append(f"Missing fuel types: {', '.join(sorted(missing))}")
        if write_errors:
            lines.append("DB write failed for: " + "; ".join(write_errors))
        await notifier.send("*Fuel scrape partial* (dgeg)\n" + "\n".join(lines))
        if missing:
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
