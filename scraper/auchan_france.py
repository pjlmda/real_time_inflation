"""Auchan France scraper — Drive locations only (docs/france-expansion-plan.md).

Not the same commerce platform as Auchan Portugal — none of scraper/auchan.py's
selectors transfer. Confirmed live 2026-07-09 via real Playwright sessions:
not bot-blocked, but no price is shown anywhere on the site (search results
or PDP) until a delivery zone is confirmed once per session. That
confirmation flow is the real complication here and is what most of this
module exists to drive.

Two Drive locations are tracked, not one — a single postcode's prices
aren't representative of "France" any more than a single store would be of
Portugal, and Drive prices are genuinely local (confirmed: the same product
priced differently in Paris vs. Marseille on the same day). Both are named,
public pickup locations — no personal data or fabricated address involved.
"Livraison à domicile" (home delivery) was considered and rejected: unlike
Drive, confirming it demands a full street address, not just a postcode.

Confirmed live and used directly here:
  - Session flow: open any product page -> click "Afficher le prix" -> fill
    the postcode input -> click the exact-text city suggestion (e.g.
    "Paris 75001") -> click the "Drive" tab button -> click the first
    plain-text "Choisir" button (nearest Drive point to that postcode).
    Playwright sees a transient overlay over that last button, hence
    force=True. This must run once per persistent browser context, before
    any real listing fetch — done here as a _build_context override.
  - Price extraction: `[itemprop='price']` is a `<meta content="...">` tag
    (schema.org Product/Offer microdata) once a Drive location is set —
    reliable, structured, no DOM-text-scraping needed for the headline
    price. `[itemprop='priceCurrency']` confirms EUR.
  - Price-per-unit: a plain, class-less `<span>` reading e.g. "1,63€ / l"
    right below the price — matched by text pattern, not class, since it
    has no distinguishing class attribute at all.
  - Out-of-stock: confirmed live via a real discontinued-at-this-location
    product, "Ce produit n'est plus dans notre gamme" ("This product is no
    longer in our range").

NOT yet confirmed live — no promoted product was encountered during
research, so this is a best-effort default, not a verified selector:
  - regular_price/is_promotion detection defaults to "no promotion" for
    every listing. This needs revisiting against a real promoted product
    before promo tracking here can be trusted, the same way Auchan
    Portugal's promo selector was initially wrong until checked against a
    live promoted product (see scraper/auchan.py's own module docstring).
"""
from __future__ import annotations

import re

from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

# postcode -> the exact autocomplete suggestion text to click (confirmed
# live: "<City> <postcode>", an exact string match, not a substring).
DRIVE_LOCATIONS = {
    "auchan-fr-paris": {
        "postcode": "75001",
        "suggestion_text": "Paris 75001",
        "expected_location_name": "Auchan Drive Supermarché Buttes Chaumont - Paris",
    },
    "auchan-fr-marseille": {
        "postcode": "13001",
        "suggestion_text": "Marseille 13001",
        "expected_location_name": "Auchan Drive Supermarché Marseille Saint-Lazare",
    },
}

# A bootstrap page used purely to open the "Afficher le prix" modal that
# starts the delivery-zone flow — it does not need to be in stock at the
# eventual chosen location (confirmed: this exact product is discontinued
# at both tracked locations, and the bootstrap flow works regardless, since
# the modal opens before any location/availability is known).
BOOTSTRAP_PRODUCT_URL = "/auchan-lait-demi-ecreme-sterilise-uht/pr-C1171534"

OUT_OF_STOCK_TEXT = "Ce produit n'est plus dans notre gamme"
PRICE_PER_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*€\s*/\s*([a-zA-Z]+)", re.IGNORECASE)
UNIT_ABBREV_MAP = {"l": "L", "kg": "kg", "g": "g", "ml": "mL", "cl": "cL", "u": "un", "pce": "un"}


class AuchanFranceScraper(BaseScraper):
    async def _build_context(self, playwright):
        context = await super()._build_context(playwright)
        page = await context.new_page()
        await self._establish_drive_location(page)
        await page.close()
        return context

    async def _establish_drive_location(self, page: Page) -> None:
        location = DRIVE_LOCATIONS[self.config.slug]

        await page.goto(f"{self.config.base_url}{BOOTSTRAP_PRODUCT_URL}", wait_until="domcontentloaded", timeout=30_000)
        await self._dismiss_cookie_banner(page)

        show_price_btn = page.locator("button:has-text('Afficher le prix')")
        if await show_price_btn.count() == 0:
            # Already has a Drive location set from a prior session in this
            # same persistent context (user_data_dir) — nothing to do.
            return

        await show_price_btn.first.click(timeout=10_000)
        await page.wait_for_timeout(1000)
        await page.locator("input[placeholder*='postal']").first.fill(location["postcode"])
        await page.wait_for_timeout(1000)
        await page.get_by_text(location["suggestion_text"], exact=True).first.click(timeout=10_000)
        await page.wait_for_timeout(1500)
        await page.get_by_role("button", name="Drive").first.click(timeout=10_000)
        await page.wait_for_timeout(1000)
        # First plain-text "Choisir" button = nearest Drive point to the
        # postcode just entered. An overlay transiently covers it, hence
        # force=True (confirmed safe live — the click still lands correctly).
        await page.locator("button").filter(has_text=re.compile(r"^Choisir$")).first.click(
            timeout=10_000, force=True
        )
        await page.wait_for_timeout(1500)

    @staticmethod
    async def _dismiss_cookie_banner(page: Page) -> None:
        try:
            await page.get_by_text("Accepter", exact=False).first.click(timeout=3000)
        except Exception:  # noqa: BLE001 - banner may not appear on every session; not fatal either way
            pass

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
        if OUT_OF_STOCK_TEXT in await page.content():
            raise FetchFailed(f"listing {listing.id} not carried at this Drive location")

        price_locator = page.locator("[itemprop='price']").first
        if await price_locator.count() == 0:
            raise FetchFailed(
                f"no price microdata found for listing {listing.id} "
                "(delivery zone not set, or selectors need review)"
            )
        price_content = await price_locator.get_attribute("content")
        if not price_content:
            raise FetchFailed(f"price microdata had no content attribute for listing {listing.id}")
        price = float(price_content)

        # Not yet confirmed against a real promoted product (see module
        # docstring) — defaults to "no promotion" until verified live.
        regular_price = price
        is_promotion = False

        ppu_text = await self._find_price_per_unit_text(page)
        price_per_unit, unit_basis = parse_price_per_unit(ppu_text) if ppu_text else (price, "EUR/unit")

        return ScrapedPrice(
            price=price,
            regular_price=regular_price,
            price_per_unit=price_per_unit,
            unit_basis=unit_basis,
            is_promotion=is_promotion,
            promotion_label=None,
            in_stock=True,
            raw_payload={"source": "microdata", "ppu_text": ppu_text},
        )

    @staticmethod
    async def _find_price_per_unit_text(page: Page) -> str | None:
        # No distinguishing class attribute at all on this element (confirmed
        # live) — matched by its text pattern instead.
        locator = page.locator("xpath=//*[contains(text(), '€ /')]").first
        if await locator.count() == 0:
            return None
        return (await locator.text_content() or "").strip()


def parse_price_per_unit(text: str) -> tuple[float, str]:
    match = PRICE_PER_UNIT_RE.search(text.replace("\xa0", " "))
    if not match:
        raise FetchFailed(f"could not parse price-per-unit from text: {text!r}")
    value = float(match.group(1).replace(",", "."))
    abbrev = match.group(2).lower()
    unit = UNIT_ABBREV_MAP.get(abbrev, abbrev)
    return value, f"EUR/{unit}"
