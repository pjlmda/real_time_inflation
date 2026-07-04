"""CLI entrypoint used both locally and by .github/workflows/scrape.yml.

Usage: `python -m scraper.run --store continente [--dry-run]`
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
from scraper.continente import ContinenteScraper
from scraper.db import SupabaseWriter
from scraper.pingodoce import PingoDoceScraper
from scraper.store_config import load_store_config

SCRAPERS = {
    "continente": ContinenteScraper,
    "pingo-doce": PingoDoceScraper,
    # auchan / lidl: added once the widened pilot is verified (spec §11).
}


async def _main(store_slug: str, dry_run: bool) -> int:
    load_dotenv()

    config = load_store_config(store_slug)
    scraper_cls = SCRAPERS.get(store_slug)
    if scraper_cls is None:
        print(f"No scraper implemented for store {store_slug!r}", file=sys.stderr)
        return 2

    supabase_client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    db = SupabaseWriter(supabase_client)

    if dry_run:
        listings = db.get_active_listings(db.get_store_id(store_slug))
        print(f"[dry-run] {len(listings)} active listing(s) for {store_slug}")
        return 0

    notifier: Notifier
    telegram_token, telegram_chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get(
        "TELEGRAM_CHAT_ID"
    )
    if telegram_token and telegram_chat_id:
        notifier = TelegramNotifier(token=telegram_token, chat_id=telegram_chat_id)
    else:
        print(
            "WARNING: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set — alerts will only "
            "print to the console, not reach Telegram.",
            file=sys.stderr,
        )
        notifier = ConsoleNotifier()

    scraper = scraper_cls(config, db, notifier, proxy_url=os.environ.get("PROXY_URL"))
    result = await scraper.run(mode="basket")
    print(
        f"store={store_slug} status={result.status} attempted={result.attempted} "
        f"ok={result.ok} failed={result.failed} coverage={result.coverage:.0%}"
    )
    # Expected failure modes (partial/failed) are alerted via Telegram, not a
    # non-zero exit — only genuinely unhandled exceptions should fail the
    # Action step so GitHub's native failure email stays a backup signal.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, choices=list(SCRAPERS.keys()))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.store, args.dry_run)))


if __name__ == "__main__":
    main()
