"""Lidl France scraper (docs/germany-expansion-plan.md's sequencing reason
for building this first: robots.txt/platform similarity to Lidl Germany).

Confirmed live 2026-07-11 via real Playwright sessions:
  - Not bot-blocked (200 OK throughout, no CAPTCHA/block markers).
  - Unlike Auchan France, prices are shown directly — no delivery-zone
    confirmation step, no location gating. One national price, same model
    as the Portuguese stores.
  - Product tiles on search/category pages carry a `data-gridbox-impression`
    attribute — URL-encoded JSON with id/name/brand/price already
    structured (`scraper/lidl_france.py` doesn't rely on this for the
    per-listing fetch, since that's search-result-only, but it's how the
    basket was curated — see seed/README.md).
  - PDP price block uses clean, stable class names:
    `.ods-price__value` (current/effective price), `.ods-price__stroke-price`
    (regular/pre-promo price, only present when a promo is active — confirmed
    live against a real -30% cheese promo, unlike Auchan France where no live
    promo was ever encountered), `.ods-price__footer` (package size + price
    per unit, e.g. "500 g\\n1 kg = 6,70 €").
  - EAN is not reliably reachable — it exists somewhere in a Nuxt-style
    flattened SSR JSON payload (an `"eans"` key pointing at an array index,
    not the barcode value directly) that isn't worth reverse-engineering for
    a pilot basket. Listings use `match_method='manual'`/`ean='TODO'`, the
    same convention already used elsewhere in this project when an EAN isn't
    available (see e.g. seed/listings.csv's Pingo Doce soap entry).
"""
from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

# "500 g", "3 x 500 g", "8 x 125 g", "1 L", "2 x 425 ml" -> (total_size, unit_basis_suffix).
# Multi-packs use the TOTAL size (count x each), matching this project's
# established convention (e.g. seed/products.csv's "Iogurte Auchan Natural
# 4x125g" -> package_size=500).
PACKAGE_SIZE_RE = re.compile(r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(g|kg|ml|cl|l)\b", re.IGNORECASE)
PRICE_PER_UNIT_RE = re.compile(r"1\s*(kg|l)\s*=\s*(\d+(?:[.,]\d+)?)\s?€", re.IGNORECASE)
UNIT_ABBREV_MAP = {"g": "g", "kg": "kg", "ml": "mL", "cl": "cL", "l": "L"}

# Variable-weight items (fresh meat sold by the kilo) show "Le kilo" instead
# of a fixed package size in the footer — confirmed live for a beef cut.
PER_KILO_MARKER = "le kilo"


class LidlFranceScraper(BaseScraper):
    async def fetch_listing(self, page: Page, listing: Listing) -> ScrapedPrice:
        response = await page.goto(listing.url, wait_until="domcontentloaded", timeout=30_000)
        if response is not None and response.status in RETRYABLE_STATUS:
            retry_after = None
            header = response.headers.get("retry-after")
            if header and header.isdigit():
                retry_after = float(header)
            raise RetryableHttpError(status=response.status, retry_after=retry_after)

        # detect_block() against raw page.content() produced a real false
        # positive here, confirmed live: Lidl's Nuxt runtime config ships a
        # `friendlyCaptchaSitekey` value in an embedded <script> JSON blob on
        # every single page load (for a form elsewhere on the site, not this
        # page), which trips the generic "captcha" marker even though
        # nothing is actually blocked. Checking rendered visible text instead
        # of raw HTML avoids it — a real block/CAPTCHA page's markers are
        # meant to be human-readable text, never JS config values.
        visible_text = await page.inner_text("body")
        if detect_block(visible_text):
            raise BlockDetected(f"block/CAPTCHA page detected for listing {listing.id}")

        await self._dismiss_consent(page)
        return await self._extract_price_block(page, listing)

    @staticmethod
    async def _dismiss_consent(page: Page) -> None:
        # Two independent consent dialogs have been observed live: a cookie
        # banner on first visit in a session, and a separate personal-data
        # dialog that can appear per-page. Both use the same button label.
        try:
            await page.get_by_role("button", name="TOUT ACCEPTER").first.click(timeout=3000)
        except Exception:  # noqa: BLE001 - dialog may not appear every time; not fatal either way
            pass

    async def _extract_price_block(self, page: Page, listing: Listing) -> ScrapedPrice:
        price_locator = page.locator(".ods-price__value").first
        if await price_locator.count() == 0:
            raise FetchFailed(f"no price element found for listing {listing.id} (selectors need review)")
        price = _parse_euro(await price_locator.inner_text())

        stroke_locator = page.locator(".ods-price__stroke-price").first
        has_stroke = await stroke_locator.count() > 0
        regular_price = _parse_euro(await stroke_locator.inner_text()) if has_stroke else price
        is_promotion = has_stroke

        promotion_label = None
        if is_promotion and regular_price > 0:
            pct_off = round((1 - price / regular_price) * 100)
            promotion_label = f"-{pct_off}%"

        footer_locator = page.locator(".ods-price__footer").first
        footer_text = (await footer_locator.inner_text()) if await footer_locator.count() > 0 else ""
        price_per_unit, unit_basis = _parse_footer(footer_text, price)

        return ScrapedPrice(
            price=price,
            regular_price=regular_price,
            price_per_unit=price_per_unit,
            unit_basis=unit_basis,
            is_promotion=is_promotion,
            promotion_label=promotion_label,
            in_stock=True,
            raw_payload={"source": "dom", "footer_text": footer_text},
        )


def _parse_euro(text: str) -> float:
    match = re.search(r"(\d+(?:[.,]\d+)?)", text.replace("\xa0", " "))
    if not match:
        raise FetchFailed(f"could not parse a euro amount from text: {text!r}")
    return float(match.group(1).replace(",", "."))


def _parse_footer(footer_text: str, price: float) -> tuple[float, str]:
    """(price_per_unit, unit_basis) from the footer block, e.g. '750 g\\n1 kg
    = 1,60 €\\n' -> (1.60, 'EUR/kg'). Variable-weight items ('Le kilo', no
    fixed package) use the listing's own price directly as its per-kilo rate."""
    if PER_KILO_MARKER in footer_text.lower():
        return price, "EUR/kg"

    ppu_match = PRICE_PER_UNIT_RE.search(footer_text)
    if ppu_match:
        unit = UNIT_ABBREV_MAP.get(ppu_match.group(1).lower(), ppu_match.group(1))
        value = float(ppu_match.group(2).replace(",", "."))
        return value, f"EUR/{unit}"

    # Fall back to deriving price-per-unit from the package size line alone
    # if no explicit "1 kg/L = X €" line was present.
    size_match = PACKAGE_SIZE_RE.search(footer_text)
    if size_match:
        count = int(size_match.group(1)) if size_match.group(1) else 1
        amount = float(size_match.group(2).replace(",", ".")) * count
        unit = UNIT_ABBREV_MAP.get(size_match.group(3).lower(), size_match.group(3))
        if amount > 0:
            return round(price / amount, 4), f"EUR/{unit}"

    return price, "EUR/unit"


# products.package_unit has a stricter DB check constraint than unit_basis
# does ('L', 'kg', 'un', 'g', 'ml' only, all lowercase, no 'cl') - centiliters
# convert to milliliters here rather than passing 'cl' through.
_PACKAGE_UNIT_MAP = {"g": "g", "kg": "kg", "ml": "ml", "cl": "ml", "l": "L"}
_CL_TO_ML = 10


def parse_package_size(footer_text: str) -> tuple[float, str]:
    """(total_size, package_unit) from the footer's first line, e.g.
    '3 x 500 g' -> (1500.0, 'g'), '8 x 125 g' -> (1000.0, 'g'), '1 L' ->
    (1.0, 'L'), '75 cl' -> (750.0, 'ml'). Used by seed curation, not by the
    scraper itself (package_size/package_unit are seeded once in
    products.csv, not re-derived on every scrape) - output matches the
    products.package_unit check constraint, not unit_basis's convention."""
    match = PACKAGE_SIZE_RE.search(footer_text)
    if not match:
        raise ValueError(f"could not parse a package size from text: {footer_text!r}")
    count = int(match.group(1)) if match.group(1) else 1
    amount = float(match.group(2).replace(",", ".")) * count
    raw_unit = match.group(3).lower()
    if raw_unit == "cl":
        amount *= _CL_TO_ML
    unit = _PACKAGE_UNIT_MAP.get(raw_unit, raw_unit)
    return amount, unit
