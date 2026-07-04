"""Pingo Doce scraper (spec §3, §6).

Also Salesforce Commerce Cloud, but a different (standard SFRA) theme than
Continente — different selectors, and unlike Continente there is **no EAN
exposed anywhere** on the rendered page (no JSON-LD offer, no AJAX-URL trick).
That's the exact case spec §5 anticipates: cross-store products here are
matched by curated brand/product identity (`match_method='manual'` in
seed/listings.csv), not by an EAN found on this store's own page.

DOM extraction is primary (same rationale as Continente — see that module's
docstring): `.sales`/`.strike-through` gives the promo/regular price pair,
and `product-unit-measure` gives a retailer-computed price-per-unit, neither
available via JSON-LD here (which only carries name/brand/sku/image, no
`offers` block at all on this site).
"""
from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

NAME_SELECTOR = "h1.product-name"
BRAND_SELECTOR = "h1.product-brand"
UNIT_MEASURE_SELECTOR = "h1.product-unit-measure"
SALES_VALUE_SELECTOR = ".prices .price .sales .value"
REGULAR_VALUE_SELECTOR = ".prices .price .strike-through.list .value"
# Best-effort guess, not yet confirmed against a real out-of-stock page —
# same situation Continente's OUT_OF_STOCK_SELECTORS started in.
OUT_OF_STOCK_SELECTORS = [".product-unavailable", ".out-of-stock"]

# "0,9 €/L", "2,52 €/Kg", "0,26 €/Un" — one or two decimal digits, unit
# abbreviation varies in case.
PRICE_PER_UNIT_RE = re.compile(r"(\d+)[.,](\d+)\D*?/\s*([a-zA-Z]+)")
UNIT_ABBREV_MAP = {"l": "L", "kg": "kg", "un": "un"}


class PingoDoceScraper(BaseScraper):
    async def fetch_listing(self, page: Page, listing: Listing) -> ScrapedPrice:
        response = await page.goto(listing.url, wait_until="domcontentloaded", timeout=30_000)
        if response is not None and response.status in RETRYABLE_STATUS:
            retry_after = None
            header = response.headers.get("retry-after")
            if header and header.isdigit():
                retry_after = float(header)
            raise RetryableHttpError(status=response.status, retry_after=retry_after)

        html = await page.content()
        if detect_block(html):
            raise BlockDetected(f"block/CAPTCHA page detected for listing {listing.id}")

        return await self._extract_price_block(page, listing)

    async def _extract_price_block(self, page: Page, listing: Listing) -> ScrapedPrice:
        sales_locator = page.locator(SALES_VALUE_SELECTOR).first
        if await sales_locator.count() == 0:
            raise FetchFailed(f"no price found for listing {listing.id} (selectors need review)")
        price_content = await sales_locator.get_attribute("content")
        if not price_content:
            raise FetchFailed(f"price value had no content attribute for listing {listing.id}")
        price = float(price_content)

        regular_locator = page.locator(REGULAR_VALUE_SELECTOR).first
        is_promotion = await regular_locator.count() > 0
        if is_promotion:
            regular_content = await regular_locator.get_attribute("content")
            regular_price = float(regular_content) if regular_content else price
        else:
            regular_price = price

        unit_measure_locator = page.locator(UNIT_MEASURE_SELECTOR).first
        unit_measure_text = (
            (await unit_measure_locator.text_content()) or ""
        ).strip() if await unit_measure_locator.count() > 0 else ""
        price_per_unit, unit_basis = _parse_unit_measure(unit_measure_text, fallback_price=price)

        promotion_label = None
        if is_promotion and regular_price > 0:
            pct_off = round((1 - price / regular_price) * 100)
            promotion_label = f"-{pct_off}%"

        out_of_stock = await self._any_visible(page, OUT_OF_STOCK_SELECTORS)

        return ScrapedPrice(
            price=price,
            regular_price=regular_price,
            price_per_unit=price_per_unit,
            unit_basis=unit_basis,
            is_promotion=is_promotion,
            promotion_label=promotion_label,
            in_stock=not out_of_stock,
            raw_payload={
                "source": "dom",
                "ean_exposed": False,
                "unit_measure_text": unit_measure_text,
            },
        )

    @staticmethod
    async def _any_visible(page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            if await page.locator(selector).count() > 0:
                return True
        return False


def _parse_unit_measure(text: str, fallback_price: float) -> tuple[float, str]:
    """`"1 L | 0,9 €/L"` -> (0.9, "EUR/L"). Only the price-per-unit half (after
    `|`) is used — package size/unit is static product metadata already
    stored in `products`, not re-derived from each scrape."""
    match = PRICE_PER_UNIT_RE.search(text.replace("\xa0", " "))
    if not match:
        return fallback_price, "EUR/unit"
    value = float(f"{match.group(1)}.{match.group(2)}")
    abbrev = match.group(3).lower()
    unit = UNIT_ABBREV_MAP.get(abbrev, abbrev)
    return value, f"EUR/{unit}"
