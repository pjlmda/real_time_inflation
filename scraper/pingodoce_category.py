"""Pingo Doce category crawler (spec §4.6).

Its category *navigation* is entirely disallowed cgid Search-Show URLs (its
own robots.txt), so products are discovered from its product sitemaps
instead (same method used for its fixed-basket curation, see
seed/README.md) and matched against `config/category_urls.yaml`'s
path_prefix/keywords. Capped at SAMPLE_CAP products per category (each
visited individually, like the fixed-basket scraper) to keep total request
volume reasonable per spec §7's "~100 pages/store/day is gentle" alongside
its 12 fixed-basket listings.
"""
from __future__ import annotations

import asyncio
import random
import re

import httpx
from playwright.async_api import Page

from scraper.antibot import RobotsChecker
from scraper.category_base import CategoryCrawlerBase
from scraper.pingodoce import (
    PRICE_PER_UNIT_RE,
    SALES_VALUE_SELECTOR,
    UNIT_MEASURE_SELECTOR,
    WEIGHT_ONLY_RE,
    parse_unit_measure,
)

SITEMAP_URLS = [
    "https://www.pingodoce.pt/home/sitemap_0-product.xml",
    "https://www.pingodoce.pt/home/sitemap_1-product.xml",
]
LOC_RE = re.compile(r"<loc>([^<]+)</loc>")
SAMPLE_CAP = 15


def _matches(url: str, category_config: dict) -> bool:
    exclude_keywords = category_config.get("exclude_keywords", [])
    if any(kw in url for kw in exclude_keywords):
        return False
    path_prefix = category_config.get("path_prefix")
    if path_prefix:
        return path_prefix in url
    keywords = category_config.get("keywords", [])
    return any(kw in url for kw in keywords)


class PingoDoceCategoryCrawler(CategoryCrawlerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sitemap_urls: list[str] | None = None

    async def fetch_category_prices(
        self,
        page: Page,
        robots: RobotsChecker,
        delay_range: tuple[float, float],
        ecoicop2_code: str,
        category_config: dict,
    ) -> list[float]:
        all_urls = await self._get_sitemap_urls()
        candidate_urls = [u for u in all_urls if _matches(u, category_config)]

        prices: list[float] = []
        for url in candidate_urls[:SAMPLE_CAP]:
            if not robots.allowed(url):
                continue
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:  # noqa: BLE001 - one bad product page shouldn't abort the sample
                await asyncio.sleep(random.uniform(*delay_range))
                continue

            sales_locator = page.locator(SALES_VALUE_SELECTOR).first
            unit_locator = page.locator(UNIT_MEASURE_SELECTOR).first
            if await sales_locator.count() > 0 and await unit_locator.count() > 0:
                sales_content = await sales_locator.get_attribute("content")
                unit_text = ((await unit_locator.text_content()) or "").strip()
                # Only include products where the unit-measure text actually
                # carries usable signal (an embedded price-per-unit, or at
                # least a parseable weight for parse_unit_measure to divide
                # the sales price by) — otherwise parse_unit_measure's final
                # fallback would silently inject a raw absolute price into
                # what's supposed to be a price-*per-unit* sample.
                has_signal = bool(
                    PRICE_PER_UNIT_RE.search(unit_text) or WEIGHT_ONLY_RE.search(unit_text)
                )
                if sales_content and has_signal:
                    price_per_unit, _basis = parse_unit_measure(
                        unit_text, fallback_price=float(sales_content)
                    )
                    prices.append(price_per_unit)

            await asyncio.sleep(random.uniform(*delay_range))
        return prices

    async def _get_sitemap_urls(self) -> list[str]:
        """Fetches both product sitemaps once per crawl run and caches the
        result on the instance — CategoryCrawlerBase.run() calls
        fetch_category_prices once per configured category on the same
        crawler instance, and re-fetching the full ~15,600-URL sitemap fresh
        for every one of those calls was wasteful. (The actual root cause of
        two categories once returning zero/few matches turned out to be
        unrelated — fresh/weight-sold items showing no embedded
        price-per-unit at all, fixed via parse_unit_measure's weight-only
        fallback above — but avoiding six redundant multi-MB refetches is
        worth keeping regardless.)"""
        if self._sitemap_urls is not None:
            return self._sitemap_urls
        urls: list[str] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sitemap_url in SITEMAP_URLS:
                resp = await client.get(sitemap_url)
                resp.raise_for_status()
                urls.extend(LOC_RE.findall(resp.text))
        self._sitemap_urls = urls
        return urls
