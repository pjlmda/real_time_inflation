"""Wegmans (US) scraper (docs/us-expansion-plan.md).

Confirmed live 2026-07-11 via real Playwright sessions:
  - Not bot-blocked. `robots.txt` is `Allow: /` unconditional, the cleanest
    of the 17 US chains checked in the expansion research; zero enterprise
    bot-mitigation cookies (`_abck`, `bm_sz`, `_pxhd`, `_px3`, `incap_ses`,
    `reese84`, `__cf_bm`, `datadome`) appeared across a full session.
  - Prices show directly, no delivery-zone confirmation step like Auchan
    France's Drive flow — a store location ("Medford") is shown by default
    without any explicit interaction, and stayed consistent across three
    sessions with different `timezone_id` contexts. Whether that default is
    IP-geolocation-based (and so could resolve differently from a GitHub
    Actions runner's real IP) or a fixed site-wide default wasn't fully
    settled — a real, disclosed risk, not assumed away. If a scheduled run
    ever shows an implausible/empty location, that's the first thing to
    check; low coverage from a location mismatch would still surface via
    the normal `coverage < 0.85` alert, not fail silently.
  - PDP price block: `.component--product-price.appearance-pdp .price`
    (e.g. "Price is:\\n$2.99/ea") and the sibling `.price-per-unit`
    (e.g. "Unit price is:\\n($2.99/gallon)") — both scoped to
    `.appearance-pdp` specifically, since a PDP also renders many other
    `.price`/`.price-per-unit` blocks for cross-sell/related-item tiles
    elsewhere on the same page (confirmed live: an unscoped `.price`
    locator matched 21 elements on one PDP, not 1).
  - UPC is available, unlike Lidl France/Germany's EAN situation — embedded
    in an inline JSON payload as `\\"upc\\":[\\"<code>\\"]` (backslash-escaped,
    since it's JSON-stringified inside a script tag, not a plain attribute).
    Produce items (fruit/veg) use a zero-padded PLU-style code in the same
    slot rather than a true 12-digit UPC-A — stored as-is; `match_method`
    is still `ean` for consistency with the rest of the schema, since the
    field plays the same barcode-identity role regardless of code family.
  - Price-per-unit is kept in Wegmans' own native US customary units
    (`USD/gallon`, `USD/lb.`, `USD/ounce`, `USD/fl. oz.`, `USD/ea`) rather
    than force-converted to metric — `unit_basis` is stored/displayed
    as-observed elsewhere in this project too (e.g. Lidl France keeps
    `EUR/mL`/`EUR/cL` natively rather than normalizing everything to L),
    and nothing in `metrics/`/`web/api/` parses the unit suffix
    programmatically, only `products.package_unit` (a separate field) is
    schema-constrained.

NOT yet confirmed live — no promoted/sale product was encountered during
basket curation research (14 categories, 58 products, no category listing
page or the site's Digital Coupons page — itself sign-in-gated — turned up
a live promo), so `regular_price`/`is_promotion` default to "no promotion"
here, the same honest starting state Auchan France's first build shipped
with before a real promoted product was found. Needs revisiting against a
real discounted product before promo tracking here can be trusted.
"""
from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

PRICE_SELECTOR = ".component--product-price.appearance-pdp .price"
PPU_SELECTOR = ".component--product-price.appearance-pdp .price-per-unit"

PRICE_RE = re.compile(r"\$(\d+(?:\.\d+)?)")
PPU_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*/\s*([a-zA-Z.\s]+?)\)?$")


class WegmansScraper(BaseScraper):
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
        # Unlike every other store scraped so far, Wegmans' price block is
        # hydrated client-side after the initial DOM (confirmed live: a
        # plain page.locator(...).count() check immediately after
        # domcontentloaded reliably found 0 elements even though the exact
        # same selector worked during research, which always waited a few
        # seconds before checking) - an explicit wait_for is required here,
        # not just count().
        price_locator = page.locator(PRICE_SELECTOR).first
        try:
            await price_locator.wait_for(state="attached", timeout=10_000)
        except Exception:  # noqa: BLE001 - Playwright's TimeoutError; genuinely absent, not a transient hiccup
            raise FetchFailed(f"no price element found for listing {listing.id} (selectors need review)")
        price_text = await price_locator.inner_text()
        price = _parse_price(price_text)

        ppu_locator = page.locator(PPU_SELECTOR).first
        ppu_text = await ppu_locator.inner_text() if await ppu_locator.count() > 0 else ""
        price_per_unit, unit_basis = _parse_ppu(ppu_text, price)

        return ScrapedPrice(
            price=price,
            regular_price=price,
            price_per_unit=price_per_unit,
            unit_basis=unit_basis,
            is_promotion=False,
            promotion_label=None,
            in_stock=True,
            raw_payload={"source": "dom", "price_text": price_text, "ppu_text": ppu_text},
        )


def _parse_price(text: str) -> float:
    match = PRICE_RE.search(text)
    if not match:
        raise FetchFailed(f"could not parse a USD amount from text: {text!r}")
    return float(match.group(1))


def _parse_ppu(ppu_text: str, price: float) -> tuple[float, str]:
    """'Unit price is:\\n($2.99/gallon)' -> (2.99, 'USD/gallon'). Falls back
    to the listing's own price/'USD/unit' if the footer has no parseable
    per-unit line (matches this project's existing per-store convention for
    an unparseable/absent price-per-unit block)."""
    match = PPU_RE.search(ppu_text.strip())
    if match:
        value = float(match.group(1))
        unit = match.group(2).strip()
        return value, f"USD/{unit}"
    return price, "USD/unit"
