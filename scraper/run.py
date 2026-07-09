"""CLI entrypoint used both locally and by .github/workflows/scrape.yml.

Usage: `python -m scraper.run --store continente [--mode basket|category] [--dry-run]`
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
from scraper.auchan import AuchanScraper
from scraper.auchan_category import AuchanCategoryCrawler
from scraper.continente import ContinenteScraper
from scraper.continente_category import ContinenteCategoryCrawler
from scraper.db import SupabaseWriter
from scraper.pingodoce import PingoDoceScraper
from scraper.pingodoce_category import PingoDoceCategoryCrawler
from scraper.store_config import load_store_config

SCRAPERS = {
    "continente": ContinenteScraper,
    "pingo-doce": PingoDoceScraper,
    "auchan": AuchanScraper,
    # lidl: added once the widened pilot is verified (spec §11).
}

CATEGORY_CRAWLERS = {
    "continente": ContinenteCategoryCrawler,
    "pingo-doce": PingoDoceCategoryCrawler,
    "auchan": AuchanCategoryCrawler,
}


async def _main(store_slug: str, mode: str, dry_run: bool) -> int:
    load_dotenv()

    config = load_store_config(store_slug)
    registry = SCRAPERS if mode == "basket" else CATEGORY_CRAWLERS
    scraper_cls = registry.get(store_slug)
    if scraper_cls is None:
        print(f"No {mode} scraper implemented for store {store_slug!r}", file=sys.stderr)
        return 2

    supabase_client = create_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"]
    )
    db = SupabaseWriter(supabase_client, timezone_id=config.timezone_id)

    if dry_run:
        if mode == "basket":
            listings = db.get_active_listings(db.get_store_id(store_slug))
            print(f"[dry-run] {len(listings)} active listing(s) for {store_slug}")
        else:
            from scraper.category_base import load_category_config

            categories = load_category_config(store_slug)
            print(f"[dry-run] {len(categories)} configured categor(y/ies) for {store_slug}")
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
    result = await scraper.run(mode="basket") if mode == "basket" else await scraper.run()
    print(
        f"store={store_slug} mode={mode} status={result.status} attempted={result.attempted} "
        f"ok={result.ok} failed={result.failed} coverage={result.coverage:.0%}"
    )
    # Expected failure modes (partial/failed) are alerted via Telegram, not a
    # non-zero exit — only genuinely unhandled exceptions should fail the
    # Action step so GitHub's native failure email stays a backup signal.
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True, choices=list(SCRAPERS.keys()))
    parser.add_argument("--mode", choices=["basket", "category"], default="basket")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args.store, args.mode, args.dry_run)))


if __name__ == "__main__":
    main()
