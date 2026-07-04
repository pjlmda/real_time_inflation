"""Auchan category crawler (spec §4.6) — direct category-listing crawl,
allowed by robots.txt (only filter/search params and account/checkout are
disallowed) and already curated by the retailer, same approach as
Continente's category crawler.
"""
from __future__ import annotations

import asyncio
import random

from playwright.async_api import Page

from scraper.antibot import RobotsChecker
from scraper.auchan import PRICE_PER_UNIT_SELECTOR, parse_price_per_unit
from scraper.category_base import CategoryCrawlerBase
from scraper.models import FetchFailed

TILE_SELECTOR = ".auc-product"


class AuchanCategoryCrawler(CategoryCrawlerBase):
    async def fetch_category_prices(
        self,
        page: Page,
        robots: RobotsChecker,
        delay_range: tuple[float, float],
        ecoicop2_code: str,
        category_config: dict,
    ) -> list[float]:
        prices: list[float] = []
        urls = category_config.get("urls", [])
        for url in urls:
            if not robots.allowed(url):
                continue
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            tiles = page.locator(TILE_SELECTOR)
            count = await tiles.count()
            for i in range(count):
                ppu_locator = tiles.nth(i).locator(PRICE_PER_UNIT_SELECTOR).first
                if await ppu_locator.count() == 0:
                    continue
                text = ((await ppu_locator.text_content()) or "").strip()
                if not text:
                    continue
                try:
                    value, _unit = parse_price_per_unit(text)
                except FetchFailed:
                    continue
                prices.append(value)
            await asyncio.sleep(random.uniform(*delay_range))
        return prices
