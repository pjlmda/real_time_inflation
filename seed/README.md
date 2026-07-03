# Seed data

`load_seed.py` upserts, in order: `stores` (from `config/stores.yaml`),
`categories` (from `categories.py`), then `products` + `product_listings`
(from `products.csv`).

## `products.csv` curation status

Continente's catalogue is client-side rendered (confirmed via WebFetch —
category pages return only navigation chrome, no product data without JS
execution), so exact product-page URLs, SKUs, and EAN barcodes could not be
fetched without a browser. The 12 pilot rows have real, verified **category**
URLs (`continente_category_url`) and realistic canonical product
names/brands/pack sizes, but `ean`, `continente_product_url`, and
`continente_sku` are placeholder `TODO` values.

`load_seed.py` handles this automatically: any row still marked `TODO` is
seeded with `product_listings.is_active = false` (using the category URL as
a placeholder `url` so the not-null constraint is satisfied) and
`match_method = 'manual'`. The scraper's active-listings query skips inactive
listings, so these rows are harmless until curated.

**To complete curation**: open each `continente_category_url` in a browser,
find the matching product, and fill in the real product page URL, the
Continente SKU (visible in the URL or page), and the EAN barcode (usually on
the product page or the physical pack) — then flip `is_active` to `true` by
re-running `load_seed.py` (it upserts on product_listings' `(product_id,
store_id)` unique key, so editing the CSV and re-running is safe/idempotent).
