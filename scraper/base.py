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
from scraper.db import SupabaseWriter, is_same_lisbon_day
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

        # scrape.yml now runs twice daily (a same-day retry a few hours after the
        # first); don't retry into a store that was explicitly block-detected
        # earlier today — that's exactly the "loop into an active block" spec §7
        # warns against, just spread across two runs instead of one. A failure
        # for any other reason (site hiccup, DB error) still retries normally.
        latest = self.db.get_latest_run(store_id, mode)
        if latest and latest.get("blocked") and is_same_lisbon_day(latest["started_at"]):
            print(
                f"Skipping {self.config.name} {mode} run — blocked earlier today, "
                "waiting for tomorrow's scheduled run instead of retrying into it."
            )
            return RunResult(
                run_id=-1,
                attempted=0,
                ok=0,
                failed=0,
                status="skipped",
                coverage=1.0,
                error_summary="skipped: blocked earlier today",
            )

        robots = RobotsChecker(self.config.base_url, self.config.user_agent)
        self.db.update_robots_checked(store_id)
        delay = max(
            self.config.delay_seconds_min, robots.crawl_delay() or self.config.delay_seconds_min
        )

        listings = self.db.get_active_listings(store_id)
        try:
            run_id = self.db.start_run(store_id, mode)
        except Exception as exc:
            # No run_id means finish_run()/mark_alerted() have nothing to update — still
            # get a Telegram signal out before re-raising, so GitHub Actions' native
            # failure email isn't the only trace of a DB outage at the start of a run.
            await self.notifier.send(
                f"*{self.config.name}* {mode} run FAILED TO START — could not write to "
                f"scrape_runs (database unreachable?): {exc}"
            )
            raise

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
                    except Exception as exc:  # noqa: BLE001 - an unexpected error (Playwright
                        # timeout, DB write failure, etc.) shouldn't silently abort the whole run
                        # past finish_run()/alerting the way an uncaught exception would — record
                        # it and keep going, same as category_base.py already does per-category.
                        failed += 1
                        error_reasons.append(f"listing {listing.id}: unexpected error: {exc}")

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
            blocked=blocked,
        )

        db_error: Exception | None = None
        try:
            self.db.finish_run(result)
        except Exception as exc:  # noqa: BLE001 - a DB write failure here shouldn't suppress
            # the alert below; still notify, then re-raise so the Action step fails and
            # GitHub's native failure email remains the backup signal.
            db_error = exc

        if (
            status in ("failed", "partial")
            or coverage < COVERAGE_ALERT_THRESHOLD
            or blocked
            or db_error is not None
        ):
            await self._alert(result, db_error=db_error)

        if db_error is not None:
            raise db_error

        return result

    async def _alert(self, result: RunResult, db_error: Exception | None = None) -> None:
        message = (
            f"*{self.config.name}* scrape run {result.status.upper()}\n"
            f"attempted={result.attempted} ok={result.ok} failed={result.failed} "
            f"coverage={result.coverage:.0%}\n"
            f"{result.error_summary or ''}"
        )
        if db_error is not None:
            message += f"\n*DB write failed while finishing this run*: {db_error}"
        await self.notifier.send(message)
        try:
            self.db.mark_alerted(result.run_id)
        except Exception:  # noqa: BLE001 - best-effort dedup flag; losing it just risks a
            # duplicate alert next time, which beats losing the alert entirely.
            pass
