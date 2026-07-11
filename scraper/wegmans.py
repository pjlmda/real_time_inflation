"""Wegmans (US) scraper (docs/us-expansion-plan.md).

**Rebuilt 2026-07-11** on `api.digitaldevelopment.wegmans.cloud`'s public
commerce JSON API, replacing the original DOM-scraping approach entirely.
Confirmed live: the exact same subdomain is called, unauthenticated, by
`wegmans.com`'s own frontend to render the public product pages everyone
already sees — this is the same "prefer parsing embedded JSON over raw
DOM-text scraping where a site exposes it" pattern this project already
uses for Continente's JSON-LD, just via a network call instead of an
embedded `<script>` tag. `robots.txt` on that subdomain 404s (no robots.txt
present at all — treated as allow-everything, the same convention
`scraper/antibot.py:RobotsChecker` already applies to any other 4xx).

Three real, decisive reasons this replaced the DOM version rather than
just adding location support on top of it:
  1. **Multi-location pricing is a real, confirmed effect, not a
     theoretical risk.** Querying the same product (Vitamin D Whole Milk,
     id 94427) at different `storeNumber`s returned $2.99/gallon at
     Medford NY (store 134) vs. $3.99/gallon at Manhattan (store 156) —
     a 33% spread — confirmed live 2026-07-11, the same class of finding
     as Auchan France's Paris-vs-Marseille discovery. The DOM version had
     no reliable way to force a specific store (the site resolves a
     default via client-side Google Geolocation API calls, not a simple
     URL/cookie parameter); the JSON API takes `storeNumber` as a plain
     query parameter, so `STORE_NUMBERS` below now maps each tracked
     location's store slug directly to a real, live-confirmed store
     number — no session/location-selector automation needed at all.
  2. **It eliminates a real disclosed risk from the original build**:
     whether the DOM version's default ("Medford", shown without any
     explicit interaction) was a fixed site-wide default or
     IP-geolocation-based, and so might resolve differently from a GitHub
     Actions runner's real IP. An explicit `storeNumber` in every request
     removes this uncertainty entirely.
  3. **It exposes real promo/loyalty price fields**
     (`price_inStoreLoyalty`, `discountType`) that no amount of DOM/text
     searching across 14 category pages ever found evidence of. Still
     **not confirmed live** — no product encountered during this session's
     research had either field populated — but the response shape is
     preserved in `raw_payload` for the next time this needs revisiting,
     which the old DOM `footer_text`/`price_text` payload couldn't offer
     nearly as cleanly.

Also fixes the client-side-hydration timing issue that broke the original
DOM version's first real run (`.count()` right after `domcontentloaded`
found nothing, since Wegmans hydrates its price block after the initial
page load) — moot now, since this is a direct API call with no rendering
step to race against at all.

Price basis: `price_inStore` (matches what the original DOM-scraped value
turned out to be, confirmed identical: $2.99 for the milk example above at
store 134) — not `price_delivery`, which runs consistently ~15-17% higher
at every store checked. In-store is the more standard basis, matching how
every other store in this project is scraped (a shelf/regular price, not a
delivery-fee-inflated one).
"""
from __future__ import annotations

import re

import httpx
from playwright.async_api import Page

from scraper.antibot import RETRYABLE_STATUS, RetryableHttpError, detect_block
from scraper.base import BaseScraper
from scraper.models import BlockDetected, FetchFailed, Listing, ScrapedPrice

COMMERCE_API_URL = "https://api.digitaldevelopment.wegmans.cloud/commerce/browse/products/"
API_VERSION = "2023-09-22"

# store slug -> Wegmans' own numeric store identifier. Each live-confirmed
# 2026-07-11 via a direct query against COMMERCE_API_URL: real, different
# in-store prices for the same product, real isSoldAtStore=true stock.
STORE_NUMBERS: dict[str, str] = {
    "wegmans-us-medford": "134",  # Long Island NY - the original build's default location
    "wegmans-us-nyc": "156",  # Manhattan - confirmed highest of the four checked
    "wegmans-us-fairfax": "16",  # Fairfax, VA - DC-metro, genuine out-of-NY-state market
    "wegmans-us-chapelhill": "140",  # Chapel Hill, NC - southernmost point in the footprint, maximally distant from NY/VA
}

UNIT_PRICE_RE = re.compile(r"\$(\d+(?:\.\d+)?)\s*/\s*(.+)$")


class WegmansScraper(BaseScraper):
    async def fetch_listing(self, page: Page, listing: Listing) -> ScrapedPrice:
        store_number = STORE_NUMBERS.get(self.config.slug)
        if store_number is None:
            raise FetchFailed(f"no Wegmans storeNumber configured for store slug {self.config.slug!r}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    COMMERCE_API_URL,
                    params={"productid": listing.store_sku, "storeNumber": store_number, "api-version": API_VERSION},
                    timeout=30.0,
                )
            except httpx.HTTPError as exc:
                raise RetryableHttpError(status=0) from exc

        if response.status_code in RETRYABLE_STATUS:
            retry_after = response.headers.get("retry-after")
            raise RetryableHttpError(
                status=response.status_code, retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None
            )
        if detect_block(response.text):
            raise BlockDetected(f"block/CAPTCHA-shaped response detected for listing {listing.id}")
        response.raise_for_status()

        payload = response.json()
        if not payload:
            raise FetchFailed(f"no product data returned for listing {listing.id} (store {store_number})")
        return _to_scraped_price(payload[0])


def _to_scraped_price(item: dict) -> ScrapedPrice:
    in_store = item.get("price_inStore") or {}
    price = in_store.get("amount")
    if price is None:
        # Confirmed live 2026-07-11: a genuine, expected outcome, not a bug -
        # e.g. fresh pork chops (product 54042) return isSoldAtStore=false,
        # price_inStore=null at the Manhattan store while carried fine at
        # Medford. Same "not every location carries every listing" gap
        # already documented for Auchan France's two Drive locations.
        if item.get("isSoldAtStore") is False:
            raise FetchFailed(f"product {item.get('productID')!r} not carried at this store ({item.get('productName')!r})")
        raise FetchFailed(f"no price_inStore.amount in response for product {item.get('productID')!r}")

    price_per_unit, unit_basis = _parse_unit_price(in_store.get("unitPrice", ""), fallback_price=price)

    # Not confirmed live (see module docstring) - structured here so a real
    # example, if one ever appears, gets picked up correctly rather than
    # silently ignored the way DOM text-search left this unconfirmed.
    loyalty_price = (item.get("price_inStoreLoyalty") or {}).get("amount")
    discount_type = item.get("discountType")
    is_promotion = bool(discount_type) or (loyalty_price is not None and loyalty_price != price)
    regular_price = price  # not yet confirmed which field represents pre-promo price - see docstring

    return ScrapedPrice(
        price=price,
        regular_price=regular_price,
        price_per_unit=price_per_unit,
        unit_basis=unit_basis,
        is_promotion=is_promotion,
        promotion_label=discount_type,
        in_stock=bool(item.get("isAvailable", True)),
        raw_payload={
            "source": "commerce-api",
            "storeNumber": item.get("storeNumber"),
            "isSoldAtStore": item.get("isSoldAtStore"),
            "price_inStore": in_store,
            "price_inStoreLoyalty": item.get("price_inStoreLoyalty"),
            "discountType": discount_type,
        },
    )


def _parse_unit_price(text: str, fallback_price: float) -> tuple[float, str]:
    """'$2.99/gallon' -> (2.99, 'USD/gallon'). Falls back to the listing's
    own price/'USD/unit' if the field is missing or unparseable."""
    match = UNIT_PRICE_RE.search(text.strip())
    if match:
        return float(match.group(1)), f"USD/{match.group(2).strip()}"
    return fallback_price, "USD/unit"
