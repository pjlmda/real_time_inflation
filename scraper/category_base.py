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
from scraper.antibot import RobotsChecker, apply_stealth
from scraper.db import SupabaseWriter
from scraper.models import CategoryStats, RunResult
from scraper.store_config import StoreConfig

COVERAGE_ALERT_THRESHOLD = 0.85
PROFILE_DIR = Path(__file__).resolve().parent.parent / ".pw-profile"
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
        launch_kwargs: dict = {
            "user_data_dir": str(PROFILE_DIR / f"{self.config.slug}-category"),
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

    async def run(self) -> RunResult:
        store_id = self.db.get_store_id(self.config.slug)
        robots = RobotsChecker(self.config.base_url, self.config.user_agent)
        self.db.update_robots_checked(store_id)
        delay_range = (
            max(
                self.config.delay_seconds_min,
                robots.crawl_delay() or self.config.delay_seconds_min,
            ),
            self.config.delay_seconds_max,
        )

        run_id = self.db.start_run(store_id, mode="category")
        attempted = ok = failed = 0
        error_reasons: list[str] = []

        async with async_playwright() as playwright:
            context = await self._build_context(playwright)
            page = await context.new_page()
            try:
                for ecoicop2_code, cat_config in self.category_config.items():
                    category_id = self.db.get_category_id(ecoicop2_code)
                    if self.db.category_already_captured_today(store_id, category_id):
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
        self.db.finish_run(result)

        if status in ("failed", "partial") or coverage < COVERAGE_ALERT_THRESHOLD:
            await self._alert(result)

        return result

    async def _alert(self, result: RunResult) -> None:
        message = (
            f"*{self.config.name}* category crawl {result.status.upper()}\n"
            f"attempted={result.attempted} ok={result.ok} failed={result.failed} "
            f"coverage={result.coverage:.0%}\n"
            f"{result.error_summary or ''}"
        )
        await self.notifier.send(message)
        self.db.mark_alerted(result.run_id)


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
