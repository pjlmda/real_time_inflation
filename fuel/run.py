"""CLI entrypoint for the fuel price scraper.

Usage: `python -m fuel.run --source dgeg` or `python -m fuel.run --source eia`

Alerts via the same Telegram notifier as the grocery scrapers on total
failure or a missing fuel type. There's no `scrape_runs` table for fuel
(no per-run `alerted` dedup) — this is a small number of runs per source,
so an unconditional send on failure is simple enough for this prototype.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

from alerting.base import Notifier, safe_send
from alerting.console import ConsoleNotifier
from alerting.telegram import TelegramNotifier, escape_markdown
from fuel.db import upsert_fuel_price
from fuel.dgeg import fetch_all_latest_prices as fetch_dgeg
from fuel.dgeg import format_unit as format_dgeg_unit
from fuel.eia import fetch_all_latest_prices as fetch_eia

# Per-source country + upsert `source` label + the fuel types a "complete"
# run is expected to cover (used for missing-type alerting below). Kept as
# per-source dicts, not one flat PT-shaped constant, now that a second
# source with a different country and fuel-type set exists.
SOURCE_COUNTRY = {"dgeg": "PT", "eia": "US"}
SOURCE_LABEL = {"dgeg": "dgeg_national_average", "eia": "eia_weekly_retail"}
ALL_FUEL_TYPES_BY_SOURCE = {
    "dgeg": {"gasoline_95", "diesel", "lpg_auto"},
    "eia": {"gasoline_regular", "diesel"},
}


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


async def _fetch_rows(source: str) -> list[dict]:
    """Returns a flat list of {fuel_type, region, date, price, unit, ...}
    rows, normalized to the shape fuel/db.py's upsert_fuel_price expects,
    regardless of which source produced them."""
    if source == "dgeg":
        results = await fetch_dgeg()
        return [
            {**row, "fuel_type": fuel_type, "region": "NATIONAL", "unit": format_dgeg_unit(row["unit"])}
            for fuel_type, row in results.items()
        ]
    return fetch_eia()  # already normalized (region/date/price/unit set)


async def _main(source: str) -> int:
    load_dotenv()
    if source not in SOURCE_COUNTRY:
        print(f"Unknown fuel source {source!r}", file=sys.stderr)
        return 2

    notifier = _build_notifier()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    try:
        rows = await _fetch_rows(source)
    except Exception as exc:  # noqa: BLE001 - broadened from EiaRequestFailed alone:
        # a Playwright timeout from fetch_dgeg(), or any other real fetch
        # failure, must still reach Telegram - narrowly catching only the
        # one exception type this module happens to raise itself would
        # leave every other failure mode silently unalerted (the exact bug
        # class this whole change set out to close).
        await safe_send(notifier, f"*Fuel scrape failed* ({source})\n{escape_markdown(str(exc))}")
        print(f"WARNING: {exc}", file=sys.stderr)
        return 1

    if not rows:
        await safe_send(notifier, f"*Fuel scrape failed* ({source})\nNo fuel prices retrieved at all.")
        print("WARNING: no fuel prices retrieved", file=sys.stderr)
        return 1

    country = SOURCE_COUNTRY[source]
    write_errors: list[str] = []
    seen_fuel_types: set[str] = set()
    for row in rows:
        fuel_type = row["fuel_type"]
        seen_fuel_types.add(fuel_type)
        try:
            upsert_fuel_price(
                client, fuel_type, row, country=country, region=row["region"], source=SOURCE_LABEL[source]
            )
            print(f"{fuel_type} [{row['region']}]: {row['date']} = {row['price']} {row['unit']}")
        except Exception as exc:  # noqa: BLE001 - one row's DB write failing shouldn't
            # skip the rest, or crash before this reaches Telegram the way an uncaught
            # exception would.
            write_errors.append(f"{fuel_type}/{row['region']}: {escape_markdown(str(exc))}")
            print(f"WARNING: failed to write {fuel_type}/{row['region']}: {exc}", file=sys.stderr)

    # Missing fuel types (site down, selector drift, API drift) or a DB
    # write failure both alert via Telegram, same as the grocery scrapers'
    # coverage-below-threshold alert (spec §8). Stays at the fuel_type
    # level, not per-PADD-region — a disclosed first-pass scope choice for
    # the eia source, not an oversight.
    missing = ALL_FUEL_TYPES_BY_SOURCE[source] - seen_fuel_types
    if missing or write_errors:
        lines = []
        if missing:
            lines.append(f"Missing fuel types: {', '.join(sorted(missing))}")
        if write_errors:
            lines.append("DB write failed for: " + "; ".join(write_errors))
        await safe_send(notifier, f"*Fuel scrape partial* ({source})\n" + "\n".join(lines))
        if missing:
            print(f"WARNING: missing fuel types: {missing}", file=sys.stderr)
        return 1

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="dgeg", choices=["dgeg", "eia"])
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.source)))


if __name__ == "__main__":
    main()
