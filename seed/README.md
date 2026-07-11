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

**Real code bug found and fixed while verifying the new categories**:
`scraper/pingodoce_category.py`'s per-product price parsing wasn't wrapped
in its own try/except (unlike the `page.goto()` call immediately above it)
— a single malformed `content` attribute (observed live as the literal
string `"null"` on one product) raised an uncaught `ValueError` that aborted
the *entire* category's sampling, not just that one product. Fixed by
wrapping just the parsing block, matching the same "one bad item shouldn't
sink the whole crawl" philosophy already used one level up.

## Cheapest-tier products for the 11 pre-existing categories

Rather than adding a "cheapest" item to every category at every store
uniformly, each store+category combination was checked against what was
already curated — 6 categories already had an own-brand/cheapest-tier
product at every store carrying them (bread, pasta, milk, eggs, poultry),
so nothing was added there; adding a near-duplicate would just dilute the
signal without adding information. The remaining genuine gaps got one
addition each, selected by **price-per-unit** where package sizes differed,
not raw price:

- **Rice** (Pingo Doce only — Continente/Auchan already own-brand):
  Arroz Agulha Europa Pingo Doce, €1.19/kg.
- **Olive oil** (Auchan only): Azeite Auchan 750ml, €3.60 — Auchan's
  existing two olive oil listings (Polegar, Oliveira da Serra PET) are
  both third-party brands with no own-brand alternative until now.
- **Cheese** (Pingo Doce + Auchan — both existing listings, Limiano and
  President, are third-party brands, not either store's own): Queijo
  Flamengo Quartos Pingo Doce (€7.73/0.35kg) and Queijo Auchan Curado
  Merendeira Light (€7.09, sold as a whole unit not by weight).
- **Canned fish** (Auchan only — its existing Tenório listing is
  third-party): Ventresca de Atum Auchan Claro em Azeite, €2.89.
- **Wine** (all 3 stores — the existing Monte Velho listing is a
  mid-range branded wine at every store, not any store's own economy
  line): Cavalo Bravo Tejo (Continente, €2.29, cheapest of ~30 tiles
  checked by price), Vinho Tinto Tejo Pingo Doce (own-brand, €1.89),
  Vinho Tinto Fonte do Nico (Auchan, €1.57 — cheapest full 0.75L bottle;
  smaller-format options existed but weren't package-comparable to the
  rest of the basket).
- **Personal care/soap** (all 3 stores — the existing Dove/Ach Brito
  listings are all name brands): Sabonete Sólido Feno (Continente,
  €3.44/360g — cheapest solid bar found among ~35 tiles, mostly liquid
  soap), Sabonete Sólido Leite e Mel Pingo Doce (own-brand, €0.59/90g),
  Sabonete Polegar Sólido 90g (Auchan, €0.49 — Polegar already used as
  Auchan's budget olive oil brand too).

11 new listings, verified live: all scraped successfully at 100% coverage,
prices matched curation research exactly. Basket now at 99 products / 109
listings across 19 categories.

## France: robustness round — 1-2 more products per category, always including the cheapest

Both France stores' baskets had exactly one product per category, which
means the within-class Jevons average had nothing to average — a single
product's price move *is* the class index. To make the class averages more
robust and to make sure each class's cheapest genuinely-available option is
represented, 1-2 more products were curated per category at both Auchan
France and Lidl France (2026-07-11), via the same live-verification
discipline as every other curation round (real search results with visible
price/price-per-unit, real PDP confirmation, no fabricated prices/URLs).

**Auchan France** (11 categories, 2 additions each = 22 new products): for
every category, both a budget/own-brand pick (Pouce — Auchan's economy
private label, distinct from the "Auchan" brand itself — or Auchan-brand
where Pouce didn't have a listing) and a recognizable national-brand pick
(Barilla, Danone, Président, Puget, Harrys, etc.) were added, so each class
mixes a discount tier and a mainstream tier. Olive oil is the one category
where the existing Auchan-brand product was already effectively the
cheapest tier live (~10€/L); the addition there (Auchan "vierge fruitée",
a genuinely different SKU/variant) is for within-class robustness, not a
new cheapest.

**Lidl France** (12 categories, 1-2 additions each = 18 new products):
followed the same `data-gridbox-impression` search-JSON curation method
proven for the original 12-product basket. Real, disclosed gaps found
during this round (same "don't force a poor-fit substitute" convention as
every prior gap in this file):
- **Pasta, beef, smoked fish, olive oil, personal care** got only 1 addition
  each, not 2 — repeated, varied search terms (e.g. "penne", "pates
  courtes" for pasta; "steak boeuf", "boeuf entrecote", "faux filet boeuf"
  for beef) turned up no second genuine product in Lidl France's own
  catalog, only unrelated non-food items or prepared/processed foods that
  were a poor category fit (sushi/onigiri for smoked fish, camping gear and
  bathroom textiles for personal care).
- **A live curation mistake was caught before it reached the seed data**:
  a "vin rouge" search result named "Fruits rouges" (€3.67) looked like a
  fruity red wine by name, but its PDP showed it priced by weight (750g,
  €/kg) rather than by volume (€/L) — the tell that it's actually a fresh
  red-fruit produce item picked up by keyword overlap ("rouge"), not wine.
  Dropped; wine got only 1 addition (Pays d'Oc Cabernet Sauvignon IGP, a
  3L bag-in-box, €5.99) instead of 2.
- **Package size wasn't always in the price footer**: 5 of the 18 Lidl
  additions (bread/7-céréales, linguine, thon fumé, cheddar râpé, tomme de
  brebis) were running a "Le 2e produit" (2nd-item) multi-buy promo, which
  replaces the footer's usual size line with the promo terms instead of
  showing the package weight. The real package size for these was found
  elsewhere in the page's visible text (a weight token near the product
  description) rather than the `.ods-price__footer` block `_parse_footer()`
  normally reads — this only affects one-off seed curation, not the
  scraper's own parsing (which doesn't need package size at scrape time).

Brand→`is_store_brand` calls for the new Lidl products follow the same
precedent set by the original 12: `L'Étal du Boucher`/`L'Étal du Volailler`
(butcher/poultry private labels), `Deluxe`, `Primadonna`, and unbranded
fresh/butcher items are Lidl's own → `true`; `Eridanous` (Lidl's Greek/
Mediterranean specialty line), `Envia` (dairy), `Chêne d'Argent` (cheese)
are treated the same way, also `true`, as they're store-specific lines not
found outside Lidl. `Aquafresh` (major external toothpaste brand) → `false`.
These are curation judgment calls, not verified against any financial
disclosure — flagged here in case a more authoritative source turns up
later.

Auchan additions are tracked at both Drive locations (Paris + Marseille),
matching the existing per-product convention. Live-verified end to end:
Lidl France 18/18 (100% coverage), Auchan Paris 33/33 (100%), Auchan
Marseille 31/33 (94% — 2 poultry listings, Duc and Le Gaulois, aren't
carried at the Marseille Drive location; a genuine regional-assortment gap,
not a bug, and still well above the 0.85 low-confidence threshold).

Basket now at 162 products / 205 listings total (up from 123/144).

## United States: Wegmans — first US store, built deep given the market's population size

`scraper/wegmans.py` built and verified live 2026-07-11, following the
research in `docs/us-expansion-plan.md` (17 US chains checked; Wegmans was
the one genuinely open door). Per explicit instruction, the basket was
curated deeper than the initial-pilot pattern used for every prior new
store (Auchan France started at 11 products/11 categories, Lidl France at
12/12) — Wegmans launched directly at **58 products across 14 categories**
(~4.1 products/category), on the reasoning that a market this much larger
in population needs more products per class for the within-class Jevons
average to be representative and stable, not just a single price series
per category.

**Categories and product counts**: rice (4), bread (4), pasta (4), beef
(4), pork (4), poultry (4), milk (4), yoghurt (4), cheese (4), eggs (4),
olive oil (4), fresh fruit (5 — apples + bananas), vegetables (5 — carrots
+ tomatoes), personal care (4). Mix of Wegmans' own store brand (roughly
70% of the basket) and recognizable national brands (Ben's Original,
Martin's, Fage, Cabot Creamery, Eggland's Best, Dove, Pantene, Head &
Shoulders, L'Oréal, Villari) for realistic brand-tier diversity, the same
discount-tier-plus-mainstream-tier mix already used for the France
robustness round.

**Two real bugs found and fixed while building this, both would have
silently corrupted data for every future store, not just Wegmans**:
- `scraper/db.py` hardcoded `"currency": "EUR"` on every `price_snapshots`
  row, for every store, unconditionally — never previously caught because
  every store built so far has been EUR-denominated. Fixed by adding
  `currency` to `StoreConfig`/`config/stores.yaml` (same pattern as the
  existing per-store `timezone_id`), threaded through `SupabaseWriter`.
  Every existing store's config entry omits the key and defaults to
  `'EUR'`, so this is additive — no existing data or behavior changes.
- `scraper/wegmans.py`'s first version checked for the price element via
  `await price_locator.count() == 0` immediately after
  `page.goto(..., wait_until="domcontentloaded")`, the same pattern used
  successfully by every other scraper in this project — but failed 57/57
  listings on the first real run (`no price element found`). Unlike every
  site scraped so far, Wegmans' price block is hydrated client-side after
  the initial DOM load (confirmed: the exact same selector worked reliably
  during research, which always paused a few seconds before checking).
  `.count()` doesn't wait for anything — it just checks what's in the DOM
  *right now*. Fixed by replacing the count check with
  `await price_locator.wait_for(state="attached", timeout=10_000)`.

**A third, smaller bug was caught before it reached real damage**: two
Wegmans products (a 5.3oz and a 32oz Greek yogurt) were both named
"0% Greek Plain Nonfat Yogurt" — identical `canonical_name`+`brand`.
`seed/load_seed.py` upserts the `products` table on `(canonical_name,
brand)`, not `product_key` — the second product's seed silently overwrote
the first's row in place rather than creating two rows, and a follow-up
fix (adding the size to each name to disambiguate) then created two *new*
rows without cleaning up the now-orphaned original, briefly leaving a
stale, unreferenced product+listing pair in the database (self-diagnosed
and deleted the same session — `products.id=1054`,
`product_listings.id=1255`). The real, general lesson: any product that
comes in multiple sizes needs the size baked into `canonical_name` itself
to stay unique under this upsert key — already done correctly elsewhere in
this project (e.g. Auchan France's "Yaourt nature 16x125g" vs "4x125g")
but missed for this one Wegmans pair.

**Not yet confirmed live**: promo/regular-price detection
(`is_promotion`/`regular_price` default to "no promotion" — no live
promoted product was found across 14 category listing pages or the site's
Digital Coupons page, which turned out to be sign-in-gated).

`python -m scraper.run --store wegmans-us --mode basket` ran for real:
**58/58 listings, 100% coverage.** (Since merged to `main` and added to
`.github/workflows/scrape.yml`'s scheduled matrix — see below.)

Real UPCs were pulled from each PDP's embedded JSON (`\"upc\":[\"<code>\"]`,
backslash-escaped since it's JSON-stringified inside a script tag) —
better barcode coverage than either Lidl France or Lidl Germany managed
(`match_method='ean'` for all 58, vs. `'manual'`/`ean='TODO'` for Lidl).
Produce items (fruit/veg) carry a zero-padded PLU-style code in the same
field rather than a true 12-digit UPC-A, since that's what Wegmans itself
uses for weight-sold produce — stored as-is.

### Wegmans, second pass same day: three locations, not one

The disclosed "is Medford's default a fixed value or IP-geolocation-based"
risk from the paragraph above turned out to matter: querying the same
product (Vitamin D Whole Milk) at different Wegmans store numbers directly
confirmed **real, substantial price variation by location** —
$2.99/gallon at Medford, NY vs. $3.99/gallon in Manhattan, a 33% spread —
the same class of finding as Auchan France's Paris-vs-Marseille discovery.
Per explicit instruction to find a solution, `scraper/wegmans.py` was
rebuilt entirely on `api.digitaldevelopment.wegmans.cloud`'s public JSON
commerce API (discovered while tracing how the site's own location
selector works) rather than DOM-scraping — it takes a `storeNumber` query
parameter directly, so tracking multiple locations no longer needs any
session/UI automation at all. `robots.txt` on that subdomain 404s (no
restriction); it's the exact same call the site's own frontend makes,
unauthenticated, to render the page every visitor sees.

Four locations now tracked and seeded: `wegmans-us-medford` (renamed from
the original `wegmans-us`, `stores.id=64` preserved so no listing
reference broke), `wegmans-us-nyc` (Manhattan), `wegmans-us-fairfax`
(Fairfax, VA — genuine out-of-NY-state market), and `wegmans-us-chapelhill`
(Chapel Hill, NC — added per explicit follow-up instruction to add a
location as geographically distant as possible from the first two states;
Chapel Hill is the southernmost point in Wegmans' whole footprint). All
four seeded with the same 58 products (437 listings total for Wegmans now,
up from 58). `wegmans-us-nyc` ran for real: **55/58 listings, 94.8%
coverage**; `wegmans-us-fairfax`: **54/58, 93%**; `wegmans-us-chapelhill`
was pre-checked before being picked (86.2%, tied with a second NC
candidate) and then ran for real minutes later at **55/58, 95%** — only
the same 3 pork products missing, not the extra dairy/personal-care items
the pre-check flagged (Wegmans' availability API reflects live inventory,
so a snapshot minutes apart can genuinely differ; noted honestly rather
than only reporting whichever number looks better). All failures confirmed
genuinely not carried at those specific stores (`isSoldAtStore: false`,
`price_inStore: null` in the API response), the same "not every location
carries every listing" gap already documented for Auchan France, not a
bug. The rebuild also incidentally surfaced that `price_delivery` runs
~15-17% higher than `price_inStore` at every store checked — confirmed the
scraper was already reading the correct basis (in-store, matching every
other country in this project) rather than an accident.

Full technical writeup (the API discovery, the three real reasons for a
full rebuild rather than a location-count bump, the promo/loyalty fields
this newly exposes) is in `docs/us-expansion-plan.md` §8, not duplicated
here.

Basket now at 220 products / 437 listings total (up from 162/205 before
Wegmans, 263 before the multi-location rebuild, 379 before the fourth
location).
