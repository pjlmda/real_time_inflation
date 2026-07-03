"""Shared scraper orchestration (spec §7, §4.5, §4.8). Concrete store
scrapers only implement `fetch_listing` — everything else (robots check,
idempotent skip, backoff, alerting, scrape_runs lifecycle) lives here once.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from alerting.base import Notifier
from scraper.antibot import RobotsChecker, apply_stealth, sleep_jitter, with_backoff
from scraper.db import SupabaseWriter
from scraper.models import BlockDetected, FetchFailed, Listing, RunResult, ScrapedPrice
from scraper.store_config import StoreConfig

COVERAGE_ALERT_THRESHOLD = 0.85
PROFILE_DIR = Path(__file__).resolve().parent.parent / ".pw-profile"


class BaseScraper(ABC):
    def __init__(
        self,
        config: StoreConfig,
        db: SupabaseWriter,
        notifier: Notifier,
        proxy_url: str | None = None,
    ):
        self.config = config
        self.db = db
        self.notifier = notifier
        self.proxy_url = proxy_url

    @abstractmethod
    async def fetch_listing(self, page: Page, listing: Listing) -> ScrapedPrice:
        """Store-specific parsing. Raise `antibot.RetryableHttpError` on
        403/429/5xx, `BlockDetected` on CAPTCHA/block pages."""

    async def _build_context(self, playwright) -> BrowserContext:
        launch_kwargs: dict = {
            "user_data_dir": str(PROFILE_DIR / self.config.slug),
            "headless": True,
            "locale": self.config.locale,
            "timezone_id": self.config.timezone_id,
            "user_agent": self.config.user_agent,
            "extra_http_headers": {"Accept-Language": "pt-PT,pt;q=0.9"},
        }
        if self.proxy_url:
            launch_kwargs["proxy"] = {"server": self.proxy_url}
        context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
        await apply_stealth(context)
        return context

    async def run(self, mode: str = "basket") -> RunResult:
        store_id = self.db.get_store_id(self.config.slug)
        robots = RobotsChecker(self.config.base_url, self.config.user_agent)
        self.db.update_robots_checked(store_id)
        delay = max(
            self.config.delay_seconds_min, robots.crawl_delay() or self.config.delay_seconds_min
        )

        listings = self.db.get_active_listings(store_id)
        run_id = self.db.start_run(store_id, mode)

        attempted = ok = failed = 0
        error_reasons: list[str] = []
        blocked = False

        async with async_playwright() as playwright:
            context = await self._build_context(playwright)
            page = await context.new_page()
            try:
                for listing in listings:
                    if self.db.listing_already_captured_today(listing.id):
                        continue
                    if not robots.allowed(listing.url):
                        failed += 1
                        error_reasons.append(f"listing {listing.id}: disallowed by robots.txt")
                        continue

                    attempted += 1
                    try:
                        scraped = await with_backoff(lambda: self.fetch_listing(page, listing))
                        self.db.upsert_snapshot(listing.id, scraped)
                        ok += 1
                    except BlockDetected:
                        failed += 1
                        error_reasons.append(f"listing {listing.id}: block/CAPTCHA detected")
                        blocked = True
                        break
                    except FetchFailed as exc:
                        failed += 1
                        error_reasons.append(f"listing {listing.id}: {exc}")

                    await sleep_jitter(delay, max(delay, self.config.delay_seconds_max))
            finally:
                await context.close()

        coverage = (ok / attempted) if attempted else 1.0
        if blocked:
            status = "failed"
        elif failed == 0:
            status = "success"
        elif ok == 0:
            status = "failed"
        else:
            status = "partial"

        result = RunResult(
            run_id=run_id,
            attempted=attempted,
            ok=ok,
            failed=failed,
            status=status,
            coverage=coverage,
            error_summary="; ".join(error_reasons[:5]) if error_reasons else None,
        )
        self.db.finish_run(result)

        if status in ("failed", "partial") or coverage < COVERAGE_ALERT_THRESHOLD or blocked:
            await self._alert(result)

        return result

    async def _alert(self, result: RunResult) -> None:
        message = (
            f"*{self.config.name}* scrape run {result.status.upper()}\n"
            f"attempted={result.attempted} ok={result.ok} failed={result.failed} "
            f"coverage={result.coverage:.0%}\n"
            f"{result.error_summary or ''}"
        )
        await self.notifier.send(message)
        self.db.mark_alerted(result.run_id)
