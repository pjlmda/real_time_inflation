"""Shared category-crawl orchestration (spec §4.6, §7) — the dynamic/
self-healing index source. Mirrors scraper/base.py's shape: concrete
crawlers only implement `fetch_category_prices`; everything else (robots
setup, idempotent same-day skip, scrape_runs lifecycle, alerting) lives
here once.
"""
from __future__ import annotations

import statistics
from abc import ABC, abstractmethod
from pathlib import Path

import yaml
from playwright.async_api import BrowserContext, Page, async_playwright

from alerting.base import Notifier
from scraper.antibot import RobotsChecker
from scraper.db import SupabaseWriter
from scraper.models import CategoryStats, RunResult
from scraper.runner_common import build_context, send_run_alert
from scraper.store_config import StoreConfig

COVERAGE_ALERT_THRESHOLD = 0.85
CATEGORY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "category_urls.yaml"
# Below this, a "category crawl" isn't a meaningful sample for median/quantiles.
MIN_PRODUCTS_FOR_STATS = 5


def load_category_config(store_slug: str) -> dict:
    raw = yaml.safe_load(CATEGORY_CONFIG_PATH.read_text(encoding="utf-8"))
    return raw.get(store_slug, {})


class CategoryCrawlerBase(ABC):
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
        self.category_config = load_category_config(config.slug)

    @abstractmethod
    async def fetch_category_prices(
        self,
        page: Page,
        robots: RobotsChecker,
        delay_range: tuple[float, float],
        ecoicop2_code: str,
        category_config: dict,
    ) -> list[float]:
        """Store-specific discovery + price-per-unit extraction for every
        product found in this category. Return whatever was found (possibly
        an empty list) rather than raising — the caller treats too few
        products as a failed category, not an exception, so one bad
        category doesn't abort the whole crawl."""

    async def _build_context(self, playwright) -> BrowserContext:
        return await build_context(playwright, self.config, self.proxy_url, profile_suffix="-category")

    async def run(self) -> RunResult:
        store_id = self.db.get_store_id(self.config.slug)
        robots = await RobotsChecker(self.config.base_url, self.config.user_agent).load()
        self.db.update_robots_checked(store_id)
        delay_range = (
            max(
                self.config.delay_seconds_min,
                robots.crawl_delay() or self.config.delay_seconds_min,
            ),
            self.config.delay_seconds_max,
        )

        try:
            run_id = self.db.start_run(store_id, mode="category")
        except Exception as exc:
            # No run_id means finish_run()/mark_alerted() have nothing to update — still
            # get a Telegram signal out before re-raising, so GitHub Actions' native
            # failure email isn't the only trace of a DB outage at the start of a run.
            await self.notifier.send(
                f"*{self.config.name}* category run FAILED TO START — could not write to "
                f"scrape_runs (database unreachable?): {exc}"
            )
            raise
        attempted = ok = failed = 0
        error_reasons: list[str] = []

        # Batched once for the whole crawl instead of two round trips
        # (get_category_id + category_already_captured_today) per configured
        # category inside the loop below.
        ecoicop2_codes = list(self.category_config.keys())
        category_id_by_code = self.db.get_category_ids(ecoicop2_codes)
        captured_today_ids = self.db.get_captured_today_category_ids(
            store_id, list(category_id_by_code.values())
        )

        async with async_playwright() as playwright:
            context = await self._build_context(playwright)
            page = await context.new_page()
            try:
                for ecoicop2_code, cat_config in self.category_config.items():
                    category_id = category_id_by_code[ecoicop2_code]
                    if category_id in captured_today_ids:
                        continue

                    attempted += 1
                    try:
                        prices = await self.fetch_category_prices(
                            page, robots, delay_range, ecoicop2_code, cat_config
                        )
                        if len(prices) < MIN_PRODUCTS_FOR_STATS:
                            failed += 1
                            error_reasons.append(
                                f"{ecoicop2_code}: only {len(prices)} product(s) found"
                            )
                            continue
                        stats = _compute_stats(prices)
                        self.db.upsert_category_observation(store_id, category_id, stats)
                        ok += 1
                    except Exception as exc:  # noqa: BLE001
                        # A single category failing (selector drift, transient
                        # error) shouldn't abort the rest of the crawl.
                        failed += 1
                        error_reasons.append(f"{ecoicop2_code}: {exc}")
            finally:
                await context.close()

        coverage = (ok / attempted) if attempted else 1.0
        status = "success" if failed == 0 else ("failed" if ok == 0 else "partial")

        result = RunResult(
            run_id=run_id,
            attempted=attempted,
            ok=ok,
            failed=failed,
            status=status,
            coverage=coverage,
            error_summary="; ".join(error_reasons[:5]) if error_reasons else None,
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
            or db_error is not None
        ):
            await self._alert(result, db_error=db_error)

        if db_error is not None:
            raise db_error

        return result

    async def _alert(self, result: RunResult, db_error: Exception | None = None) -> None:
        await send_run_alert(self.notifier, self.db, self.config.name, result, "category crawl", db_error=db_error)


def _compute_stats(prices: list[float]) -> CategoryStats:
    ordered = sorted(prices)
    p25, _, p75 = statistics.quantiles(ordered, n=4, method="inclusive")
    return CategoryStats(
        n_products=len(ordered),
        median=statistics.median(ordered),
        mean=statistics.mean(ordered),
        p25=p25,
        p75=p75,
    )
