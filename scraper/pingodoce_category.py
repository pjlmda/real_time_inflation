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
from scraper.pingodoce import PRICE_PER_UNIT_RE, UNIT_MEASURE_SELECTOR

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
    async def fetch_category_prices(
        self,
        page: Page,
        robots: RobotsChecker,
        delay_range: tuple[float, float],
        ecoicop2_code: str,
        category_config: dict,
    ) -> list[float]:
        candidate_urls = await self._discover_urls(category_config)

        prices: list[float] = []
        for url in candidate_urls[:SAMPLE_CAP]:
            if not robots.allowed(url):
                continue
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:  # noqa: BLE001 - one bad product page shouldn't abort the sample
                await asyncio.sleep(random.uniform(*delay_range))
                continue

            unit_locator = page.locator(UNIT_MEASURE_SELECTOR).first
            if await unit_locator.count() > 0:
                text = ((await unit_locator.text_content()) or "").strip().replace("\xa0", " ")
                match = PRICE_PER_UNIT_RE.search(text)
                if match:
                    prices.append(float(f"{match.group(1)}.{match.group(2)}"))

            await asyncio.sleep(random.uniform(*delay_range))
        return prices

    @staticmethod
    async def _discover_urls(category_config: dict) -> list[str]:
        urls: list[str] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for sitemap_url in SITEMAP_URLS:
                resp = await client.get(sitemap_url)
                resp.raise_for_status()
                urls.extend(LOC_RE.findall(resp.text))
        return [u for u in urls if _matches(u, category_config)]
