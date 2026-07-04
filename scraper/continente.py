"""Continente scraper (spec §3, §6).

Selectors below are verified against the live rendered site (inspected via
Playwright against several real PDPs, see seed/README.md), not guessed.
DOM extraction is the *primary* path here — deliberately inverting the
general "prefer structured data" heuristic from spec §3 — because
Continente's DOM exposes strictly more than its JSON-LD: a promo/regular
price pair (`price` vs `regular_price`, spec §6's dual price basis) and a
retailer-computed price-per-unit (`€/lt`, `€/kg`, `€/doz`), neither of which
appears in the `Product` JSON-LD block. JSON-LD is kept as a fallback for
resilience if Continente's DOM changes.
"""
from __future__ import annotations

import json
import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

PRICE_PRIMARY_SELECTOR = ".pwc-tile--price-primary"
PRICE_REGULAR_SELECTOR = ".strike-through.pwc-tile--price-dashed .value"
PRICE_PER_UNIT_SELECTOR = ".pwc-tile--price-secondary"
OUT_OF_STOCK_SELECTORS = [".out-of-stock", "[data-testid='unavailable']"]

# Continente splits the primary price across adjacent DOM nodes (e.g.
# `4<span class="decimalPrice">,09€</span>`), so text_content() can come back
# with incidental whitespace between the integer and decimal parts —
# tolerate it rather than assume the two halves are directly adjacent.
PRICE_RE = re.compile(r"(\d+)\s*[.,]\s*(\d+)")
PRICE_PER_UNIT_RE = re.compile(r"(\d+)\s*[.,]\s*(\d+)\D*?/\s*([a-zA-Z]+)")

# Continente's unit abbreviations (as shown in "€/lt", "€/kg", "€/doz") ->
# normalized unit_basis suffix.
UNIT_ABBREV_MAP = {"lt": "L", "kg": "kg", "un": "un", "doz": "doz", "cl": "cL", "g": "g", "ml": "mL"}


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

        dom_price = await self._extract_price_block(page)
        if dom_price is not None:
            return dom_price

        scripts = await page.locator("script[type='application/ld+json']").all_text_contents()
        structured = parse_json_ld(scripts)
        if structured is not None:
            return structured

        raise FetchFailed(f"no price found for listing {listing.id} (selectors need review)")

    async def _extract_price_block(self, page: Page) -> ScrapedPrice | None:
        primary_locator = page.locator(PRICE_PRIMARY_SELECTOR).first
        if await primary_locator.count() == 0:
            return None
        primary_text = ((await primary_locator.text_content()) or "").strip()
        price = _parse_price(primary_text)

        regular_locator = page.locator(PRICE_REGULAR_SELECTOR).first
        is_promotion = await regular_locator.count() > 0
        regular_price = (
            _parse_price((await regular_locator.text_content()) or "") if is_promotion else price
        )

        ppu_locator = page.locator(PRICE_PER_UNIT_SELECTOR).first
        ppu_text = ((await ppu_locator.text_content()) or "").strip() if await ppu_locator.count() > 0 else ""
        if ppu_text:
            price_per_unit, unit_basis = _parse_price_per_unit(ppu_text)
        else:
            price_per_unit, unit_basis = price, "EUR/unit"

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
                "primary_text": primary_text,
                "ppu_text": ppu_text,
                "is_promotion": is_promotion,
            },
        )

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
    return float(f"{match.group(1)}.{match.group(2)}")


def _parse_price_per_unit(text: str) -> tuple[float, str]:
    match = PRICE_PER_UNIT_RE.search(text.replace("\xa0", " "))
    if not match:
        raise FetchFailed(f"could not parse price-per-unit from text: {text!r}")
    value = float(f"{match.group(1)}.{match.group(2)}")
    abbrev = match.group(3).lower()
    unit = UNIT_ABBREV_MAP.get(abbrev, abbrev)
    return value, f"EUR/{unit}"


def parse_json_ld(scripts: list[str]) -> ScrapedPrice | None:
    """Pure function: raw `<script type="application/ld+json">` contents ->
    a ScrapedPrice from the first `Product` block with a price, or None if
    no structured data is present. Fallback path only — see module docstring
    for why DOM extraction is primary. Unit-tested against a saved fixture."""
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
