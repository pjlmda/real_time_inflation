"""Continente scraper (spec §3): prefer embedded structured data over DOM
scraping where possible, falling back to CSS selectors.

NOTE: continente.pt renders product listings/details client-side (confirmed
by fetching category pages without a browser — only navigation chrome comes
back, no product JSON). The selectors below are a best-effort starting point
and MUST be verified/adjusted against the live rendered page during the
Milestone 8 local verification pass (`python -m scraper.run --store
continente`) before this is trusted — there is no ground truth DOM available
without actually running Playwright against the site.
"""
from __future__ import annotations

import json
import re

from playwright.async_api import Page

from scraper.antibot import RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

RETRYABLE_STATUS = {403, 429, 500, 502, 503, 504}

# Candidate selectors for Continente's PDP — verify/adjust against the live
# site; kept as a ranked list so small markup changes don't require a
# redeploy, just reordering/adding a selector.
PRICE_SELECTORS = ["[data-testid='price']", ".pwc-tile--price", ".product-price"]
PRICE_PER_UNIT_SELECTORS = [".pwc-tile--pricePerUnit", ".price-per-unit"]
NAME_SELECTORS = ["h1", "[data-testid='product-name']"]
PROMO_SELECTORS = [".pwc-tile--discount", ".promotion-label"]
OUT_OF_STOCK_SELECTORS = [".out-of-stock", "[data-testid='unavailable']"]

PRICE_RE = re.compile(r"(\d+[.,]\d+)")


class ContinenteScraper(BaseScraper):
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

        structured = await self._extract_structured_data(page)
        if structured is not None:
            return structured

        return await self._extract_from_dom(page, listing)

    async def _extract_structured_data(self, page: Page) -> ScrapedPrice | None:
        """Try JSON-LD `Product`/`Offer` blocks first — cheaper and more
        stable than DOM scraping when present (spec §3)."""
        scripts = await page.locator("script[type='application/ld+json']").all_text_contents()
        return parse_json_ld(scripts)

    async def _extract_from_dom(self, page: Page, listing: Listing) -> ScrapedPrice:
        price_text = await self._first_text(page, PRICE_SELECTORS)
        if price_text is None:
            raise FetchFailed(f"no price found for listing {listing.id} (selectors need review)")

        price = _parse_price(price_text)
        promo_text = await self._first_text(page, PROMO_SELECTORS)
        out_of_stock = await self._any_visible(page, OUT_OF_STOCK_SELECTORS)
        ppu_text = await self._first_text(page, PRICE_PER_UNIT_SELECTORS)

        return ScrapedPrice(
            price=price,
            regular_price=price,
            price_per_unit=_parse_price(ppu_text) if ppu_text else price,
            unit_basis="EUR/unit",
            is_promotion=promo_text is not None,
            promotion_label=promo_text,
            in_stock=not out_of_stock,
            raw_payload={"source": "dom", "price_text": price_text, "html_snippet": price_text},
        )

    @staticmethod
    async def _first_text(page: Page, selectors: list[str]) -> str | None:
        for selector in selectors:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                text = (await locator.text_content()) or ""
                text = text.strip()
                if text:
                    return text
        return None

    @staticmethod
    async def _any_visible(page: Page, selectors: list[str]) -> bool:
        for selector in selectors:
            if await page.locator(selector).count() > 0:
                return True
        return False


def _parse_price(text: str) -> float:
    match = PRICE_RE.search(text.replace("\xa0", " "))
    if not match:
        raise FetchFailed(f"could not parse price from text: {text!r}")
    return float(match.group(1).replace(",", "."))


def parse_json_ld(scripts: list[str]) -> ScrapedPrice | None:
    """Pure function: raw `<script type="application/ld+json">` contents ->
    a ScrapedPrice from the first `Product` block with a price, or None if
    no structured data is present. Unit-tested against a saved fixture."""
    for raw in scripts:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if item.get("@type") != "Product":
                continue
            offer = item.get("offers") or {}
            price = offer.get("price")
            if price is None:
                continue
            price = float(price)
            return ScrapedPrice(
                price=price,
                regular_price=price,
                price_per_unit=price,  # normalized in a follow-up pass once package_size is known
                unit_basis="EUR/unit",
                is_promotion=False,
                promotion_label=None,
                in_stock=str(offer.get("availability", "")).endswith("InStock"),
                raw_payload={"source": "json-ld", "item": item},
            )
    return None
