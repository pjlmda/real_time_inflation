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
