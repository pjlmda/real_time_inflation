"""Auchan scraper (spec §3, §6).

Also Salesforce Commerce Cloud, SFRA-style like Pingo Doce (`.sales
.value[content]`). Unlike either existing store, Auchan exposes EAN in
three redundant places — JSON-LD `gtin`, a `data-ean` attribute, and plain
visible text (`<span class="product-ean">`) — confirmed on a live PDP, the
most reliable EAN exposure of the three stores so far.

NOTE: the promo/regular-price selector below (`.auc-price__list .value`) is
inferred from the confirmed empty-state class (`.auc-price__no-list`, seen
on every non-promo'd tile sampled) rather than a directly observed live
promo — no promo'd product was found during curation to confirm it. Flagged
here the same way Pingo Doce's out-of-stock selector was: best-effort,
needs live verification once a real Auchan promo is observed.
"""
from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

SALES_VALUE_SELECTOR = ".sales .value"
REGULAR_VALUE_SELECTOR = ".auc-price__list .value"  # inferred, see module docstring
PRICE_PER_UNIT_SELECTOR = ".auc-measures--price-per-unit"
OUT_OF_STOCK_SELECTORS = [".product-unavailable", ".out-of-stock"]

# "0.86 €/Lt", "1.63 €/Kg", "0.24 €/un" — one or two decimal digits, dot
# decimal (unlike Pingo Doce's comma). Whole numbers render with no decimal
# point at all (e.g. "1 €/Lt" for an exact €1.00/L) — decimal part optional.
PRICE_PER_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\D*?/\s*([a-zA-Z]+)")
UNIT_ABBREV_MAP = {"lt": "L", "kg": "kg", "un": "un"}


class AuchanScraper(BaseScraper):
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

        ppu_locator = page.locator(PRICE_PER_UNIT_SELECTOR).first
        ppu_text = ((await ppu_locator.text_content()) or "").strip() if await ppu_locator.count() > 0 else ""
        price_per_unit, unit_basis = parse_price_per_unit(ppu_text) if ppu_text else (price, "EUR/unit")

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
            raw_payload={"source": "dom", "ppu_text": ppu_text, "is_promotion": is_promotion},
        )

    @staticmethod
    async def _any_visible(page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            if await page.locator(selector).count() > 0:
                return True
        return False


def parse_price_per_unit(text: str) -> tuple[float, str]:
    match = PRICE_PER_UNIT_RE.search(text.replace("\xa0", " "))
    if not match:
        raise FetchFailed(f"could not parse price-per-unit from text: {text!r}")
    value = float(match.group(1))
    abbrev = match.group(2).lower()
    unit = UNIT_ABBREV_MAP.get(abbrev, abbrev)
    return value, f"EUR/{unit}"
