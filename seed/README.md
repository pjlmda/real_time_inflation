# Seed data

`load_seed.py` upserts, in order: `stores` (from `config/stores.yaml`),
`categories` (from `categories.py`), `products` (from `products.csv`), then
`product_listings` (from `listings.csv`).

## File structure

- **`products.csv`**: canonical product definitions, one row per physical
  good — `product_key` (a stable, human-readable join key), canonical_name,
  brand, is_store_brand, ecoicop2_code, package_size, package_unit, ean.
- **`listings.csv`**: one row per store-specific listing — `product_key`
  (references a row in products.csv), store_slug, url, store_sku, ean,
  match_method.

Splitting these two is what makes cross-store matching real: two
`listings.csv` rows can reference the *same* `product_key` when the same
physical product (same manufacturer, same EAN) is sold at two different
stores — `load_seed.py` resolves `product_key` → `product_id` once, so both
listings end up pointing at one `products` row instead of creating
duplicates. 5 of the current 28 products are shared this way (matched by
brand/product identity, confirmed via identical EAN): Mimosa meio-gordo milk,
Bimbo bread, and Milaneza pasta are each carried by all 3 stores; Mimosa
inteiro milk and Oliveira da Serra "Clássico" olive oil are shared between
Continente and Pingo Doce only (Auchan doesn't carry the exact same product —
its own Oliveira da Serra listing is a different EAN, a "PET" bottle variant
of the same brand, correctly kept as a separate product rather than forced
into a false match).

**Pitfall hit once already**: `products` upserts on `(canonical_name, brand)`
(migration 0001's unique constraint) — if a product_key's `canonical_name` in
`products.csv` doesn't match a pre-existing row's exact text (e.g. adding or
dropping a word), the upsert silently creates a *new* product instead of
updating the existing one, breaking the cross-store link. Keep canonical
names byte-for-byte stable once a product_key is in use elsewhere.

## Curation status: both stores curated, real data

**Continente** (12 listings): client-side rendered (plain fetches return only
nav chrome), researched via headful Playwright — category pages for
candidates, then each PDP's JSON-LD (`name`/`brand`/`sku`) plus its
net-quantity label (`emb. 1 lt`, `emb. 820 gr`, `emb. 12 un`) for
package_size/unit. EAN isn't in the JSON-LD, but is embedded in the
nutritional-info tab's AJAX URL (`...ProductNutritionalInfoTab?pid=...
&ean=...&supplierid=...`), present in the initial page render — no extra
request needed. `match_method='ean'` for all 12.

**Pingo Doce** (12 listings, added when widening past the single-store
pilot): also Salesforce Commerce Cloud, but its category *navigation* is
entirely built on `Search-Show?cgid=...` URLs that its own `robots.txt`
disallows. Product pages were instead discovered via the sitemap it
references (`sitemap_0-product.xml` / `sitemap_1-product.xml`, ~15,600 real
product URLs) — the sanctioned way to find crawlable pages here. Unlike
Continente, **no EAN is exposed anywhere** (no JSON-LD offer, no AJAX-URL
trick) — spec §5's anticipated fallback case — so all 12 Pingo Doce rows use
`match_method='manual'` except the 5 shared products, which reuse the EAN
already known from the Continente side of the match.

**Auchan** (12 listings, 3rd store): also Salesforce Commerce Cloud, SFRA-style
like Pingo Doce, but the cleanest EAN exposure of the three — present in
JSON-LD `gtin`, a `data-ean` attribute, *and* plain visible text
(`<span class="product-ean">`) simultaneously. Category listing pages are
directly crawlable (robots.txt only blocks filter/search params and
account/checkout), so curation used the same category-page approach as
Continente rather than Pingo Doce's sitemap-enumeration route.
`match_method='ean'` for all 12.

All three stores' scrapers (`scraper/continente.py`, `scraper/pingodoce.py`,
`scraper/auchan.py`) have been run against the live sites and verified: all
prices/promos/price-per-unit values landed exactly matching what was found
during curation.

## Basket growth: 6 new categories (rice, cheese, poultry, canned fish, wine, toiletries)

Added one representative product per category per store (18 listings, 16 new
products — Monte Velho red wine turned out to be carried, identically, by
all 3 stores, confirmed via matching EAN 5601989001412 at Continente and
Auchan and reused for Pingo Doce's listing since it never exposes EAN
itself). Chosen over household cleaning (spec's other under-represented
area) per user steer — protein staples matter more for a family grocery
basket than cleaning products, for this pass.

**Real gotcha hit during curation**: several sitemap-sourced Continente
product URLs (a whole chicken, a solid soap bar) turned out to be stale/
delisted — the page redirected to the generic homepage instead of 404ing,
so the failure only showed up as a missing JSON-LD `Product` block, not an
HTTP error. Always spot-check that a curated URL's JSON-LD `@type` is
actually `"Product"`, not just that the request returned 200.

**Real bug found and fixed during category-crawl verification**: Pingo
Doce's fresh/weight-sold items (talho butcher counter, charcutaria-e-queijos
cheese counter) render only a bare weight in the unit-measure element (e.g.
`"1.5 Kg"`), not the `"1 L | 0,9 €/L"` format packaged goods show — so the
price-per-unit regex correctly found nothing, but the *fixed-basket*
scraper's fallback path silently degraded these to a meaningless
`unit_basis="EUR/unit"`, and the *category crawler* excluded them entirely
(0-2 products found for poultry/cheese instead of the expected 15).
`scraper/pingodoce.py`'s `parse_unit_measure()` now recognizes weight-only
text and computes `price_per_unit = sales_price / weight` itself; the
category crawler was updated to fetch the sales price too so it can do the
same computation instead of skipping these items.

## Basket growth round 3: 8 new categories (flour, beef, pork, fresh fish,
bacalhau, yoghurt, fresh fruit, vegetables)

Added `01.1.1.2` (flour), `01.1.2.1` (beef and veal), `01.1.2.2` (pork),
`01.1.3.1` (fresh fish), `01.1.3.5` (dried/salted fish — bacalhau),
`01.1.4.4` (yoghurt), `01.1.6.1` (fresh fruit: banana/apple/orange/pear —
one leaf class covers all fresh fruit varieties) and `01.1.7.1` (vegetables:
onion/carrot/lettuce/tomato/potato). 44 new products/listings, bringing the
basket to 88 products / 98 listings across 19 ECOICOP categories.

**Deliberate simplification**: potatoes are ECOICOP's own leaf class
(`01.1.7.2`, distinct from "vegetables other than potatoes") but are folded
into `01.1.7.1` here rather than given a separate category row, per an
explicit user steer to keep this pass simpler. This means `01.1.7.1`'s HICP
weight (which officially excludes potatoes) is applied to a basket that
*does* include a potato product — a small, disclosed methodological
looseness, not a data error.

**Real bug caught before it shipped**: the plan for this round listed
Yoghurt as `01.1.4.3` — plausible, but wrong. The same verification method
used to fix the earlier Cheese/Eggs bug (Eurostat's official labels for the
exact code) showed `01.1.4.3` is actually **Preserved milk** (weight 0.68);
real Yoghurt is `01.1.4.4` (weight 5.58). Caught during curation, before any
data was written — corrected in the plan and in `seed/categories.py`
directly, so no live fix was needed this time. Lesson reinforced: never
trust a COICOP code from memory or a plausible-sounding plan — always
verify against Eurostat's own label for that exact code before seeding it.

**Real gotcha hit again**: several sitemap-sourced Auchan product URLs
(an apple, an orange, a pear — all under `produto-local` naming) returned
HTTP 200 but rendered Auchan's own "not found" page instead of a product —
the same stale-sitemap-URL class of bug already seen with Continente.
Caught by checking for an actual `.sales` price element rather than trusting
the HTTP status code; live replacement URLs were found via each category's
current listing page instead of the sitemap.

**Real gap found, not worked around**: Pingo Doce has no standalone fresh
carrot listing anywhere in its product sitemap (confirmed via full-text
search across both sitemap files, and its category landing page itself
404s — consistent with its already-known broken category navigation).
Rather than force a poor-fit substitute, carrot is 2-store coverage only
(Continente, Auchan) — the first product in this basket without Pingo Doce
representation.
