# Seed data

`load_seed.py` upserts, in order: `stores` (from `config/stores.yaml`),
`categories` (from `categories.py`), then `products` + `product_listings`
(from `products.csv`).

## `products.csv` curation status

Curated. Continente's catalogue is client-side rendered (plain fetches only
return navigation chrome, no product data), so the 12 pilot rows were
researched with a headful Playwright crawl: category pages were rendered to
find candidate products, then each product detail page was rendered to pull
its JSON-LD block (`name`, `brand`, `sku`, `price`) and its net-quantity
label (`emb. 1 lt`, `emb. 820 gr`, `emb. 12 un`, ...) for `package_size` /
`package_unit`. The EAN-13 barcode isn't in the JSON-LD, but Continente's
frontend embeds it in the nutritional-info tab's AJAX URL
(`...ProductNutritionalInfoTab?pid=...&ean=...&supplierid=...`), which is
present in the initially rendered HTML — no extra request needed.

All 12 rows have real `continente_product_url`, `continente_sku` (Continente's
internal product id), and `ean`, and are seeded as `is_active = true`,
`match_method = 'ean'`.

**Known gaps / caveats for whoever reviews the basket:**
- `regular_price` vs `price`: one PDP inspected mid-promotion (`azeite-virgem-extra-continente`)
  showed a PVPR of €4.69 vs a promotional price of €4.09 — a reminder that
  `ContinenteScraper`'s JSON-LD path currently sets `regular_price = price`
  unconditionally (see `scraper/continente.py`); the DOM-fallback path is the
  only one that currently detects promotions. Worth revisiting once real
  scrape data shows how often JSON-LD's `offers.price` is the promo price.
- Selectors in `scraper/continente.py` (`PRICE_SELECTORS` etc.) are still
  unverified against the live DOM fallback path — the JSON-LD path (now known
  to work, per the above) is what a first live scrape will actually exercise.
