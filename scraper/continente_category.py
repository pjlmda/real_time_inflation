"""Continente category crawler (spec §4.6) — direct category-listing crawl,
allowed by robots.txt and already curated by the retailer (spec §3: prefer
whatever the store already structures for us over guesswork).

Reuses PRICE_PER_UNIT_SELECTOR/`parse_price_per_unit` from scraper.continente
since Continente shows the same per-unit price on both category tiles and the
PDP (`.pwc-tile--price-secondary`), verified against a live category page.
"""
from __future__ import annotations

import asyncio
import random

from playwright.async_api import Page

from scraper.antibot import RobotsChecker
from scraper.category_base import CategoryCrawlerBase
from scraper.continente import PRICE_PER_UNIT_SELECTOR, parse_price_per_unit
from scraper.models import FetchFailed

TILE_SELECTOR = ".product[data-pid]"


class ContinenteCategoryCrawler(CategoryCrawlerBase):
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
