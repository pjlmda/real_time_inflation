# Portugal Real-Time Inflation Tracker — System Overview

Snapshot date: 2026-07-06. This document describes the system **as built and running**, not the aspirational spec — where the two differ, that's called out explicitly. The authoritative design spec remains [inflation-tracker-plan.md](../inflation-tracker-plan.md); this document is a companion status/reference doc, written before starting Phase 3 (the web app).

---

## 1. What the system does

A daily-updating grocery-inflation index for Portugal, built by scraping public online supermarket catalogue prices from three retailers (Continente, Pingo Doce, Auchan) and computing an index methodologically aligned with INE/Eurostat HICP (ECOICOP v2 classification), so results are comparable to official inflation figures. A separate, independent prototype tracks national-average fuel prices (gasoline 95, diesel, LPG auto) sourced from DGEG.

Two index families are designed in the spec (only one is built so far):
- **Fixed-basket index** (built, running daily) — a curated, EAN-matched basket of 44 products / 54 store-listings, Jevons-aggregated per ECOICOP class, HICP-weighted across classes.
- **Category-average index** (data collection built, aggregation/compute not built yet) — broader per-category price statistics (median/mean/p25/p75) from crawling whole category listing pages, intended as a robustness/self-healing check against the fixed basket. `category_observations` has been accumulating data since Phase 2 (99 rows so far) but nothing yet reads from it to produce a `category_avg` row in `inflation_metrics`.

---

## 2. Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │   GitHub Actions (scheduled + manual)        │
                    │                                               │
  06:00 UTC cron →  │  scrape.yml  (matrix: continente/pingo-doce/  │
                    │               auchan — basket + category)    │──┐
                    │                                               │  │ workflow_run
  06:00 UTC cron →  │  fuel.yml    (DGEG national average)          │  │ (on completion)
                    │                                               │  │
                    │  compute.yml (triggered by scrape.yml)   ◄────┘  │
                    └─────────────────────────────────────────────┘
                              │                    │
                              ▼                    ▼
                    ┌──────────────────────────────────────┐
                    │   Supabase Postgres (via PostgREST)   │
                    │   10 tables — see §3                  │
                    └──────────────────────────────────────┘
                              │
                              ▼
                    Telegram (alerts only — no dashboard yet)

                    Phase 3 (not started): FastAPI read-only API → Next.js web app
```

Three independent GitHub Actions workflows exist (`.github/workflows/`):

| Workflow | Trigger | Purpose |
|---|---|---|
| `scrape.yml` | cron `0 6 * * *` + `workflow_dispatch` | Per-store basket scrape + category crawl, 3 parallel matrix jobs |
| `compute.yml` | `workflow_run` on `scrape` completion + `workflow_dispatch` | Runs the Jevons index compute, writes `inflation_metrics` |
| `fuel.yml` | cron `0 6 * * *` + `workflow_dispatch` | DGEG national fuel average scrape |

All three use `astral-sh/setup-uv@v3` + `uv sync --frozen` for a reproducible Python environment (`uv.lock` pinned), and pull `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` (+ `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` where alerting applies) from GitHub Actions repo secrets. `scrape.yml`/`fuel.yml` additionally run `playwright install --with-deps chromium`; `compute.yml` doesn't (it only talks to Supabase, no browser needed).

---

## 3. Database schema (Supabase Postgres)

Applied via 3 forward-only, manually-run SQL files in `db/migrations/` (`0001_init_schema.sql`, `0002_widen_hicp_weight_precision.sql`, `0004_fuel_prices.sql` — **note: there is no `0003` file; numbering jumped 0002→0004, seemingly unintentionally, but no migration content is missing**). No migration tool (Alembic/Flyway) is used — each file is applied once by hand through the Supabase SQL editor per the `db/migrations/README.md` convention.

### 3.1 `stores`
Store registry. `id smallserial PK`, `slug text unique`, `name`, `base_url`, `robots_checked_at timestamptz`, `country default 'PT'`. 4 rows: `continente`, `pingo-doce`, `auchan` (all active), `lidl` (seeded but inactive — no scraper implemented yet).

### 3.2 `categories`
ECOICOP v2 leaf classes. `id smallserial PK`, `ecoicop2_code text unique` (e.g. `01.1.4.1`), `name_pt`/`name_en`, `parent_id → categories.id` (always null in practice — full hierarchy walk isn't needed by anything), `level`, `hicp_weight numeric(8,4)` + `weight_year` (populated only by `weights/eurostat.py`, never hand-entered). 11 rows currently.

### 3.3 `products`
The canonical fixed basket — one row per physical good, cross-store. `id serial PK`, `canonical_name`, `brand`, `is_store_brand bool`, `category_id → categories.id`, `ean text` (nullable — not every product's EAN is known/used), `package_size numeric`, `package_unit text` (check-constrained to `L/kg/un/g/ml`), `within_cat_weight numeric(8,4) default 1`, `is_active bool default true`. **Unique constraint on `(canonical_name, brand)`** — this is the upsert key `seed/load_seed.py` relies on, and the one sharp edge documented in `seed/README.md`: if a product's `canonical_name` text isn't byte-for-byte identical to what's already stored, the upsert silently creates a duplicate product instead of updating the existing (cross-store-linked) one. 44 rows.

### 3.4 `product_listings`
Store-specific identity for a product. `id serial PK`, `product_id → products.id`, `store_id → stores.id`, `store_sku`, `ean`, `url text not null`, `raw_name`, `match_method text` (check-constrained: `ean | manual | fuzzy`), `is_active bool`. **Unique `(product_id, store_id)`**. This is the join table that makes cross-store price comparison possible — 5 of the 44 products have 2–3 listings (one per store carrying that exact EAN); the rest are single-store. 54 rows.

### 3.5 `price_snapshots` — the append-only core fact table
`id bigserial PK`, `listing_id → product_listings.id`, `scrape_date date`, `scraped_at timestamptz`, `price numeric(8,2)` (effective/displayed price), `regular_price numeric(8,2)` (headline/regular price), `price_per_unit numeric(10,4)`, `unit_basis text` (e.g. `EUR/L`), `is_promotion bool`, `promotion_label text`, `in_stock bool`, `currency default 'EUR'`, **`raw_payload jsonb not null`** (the full scrape evidence — selector text, source flag, promo flag — kept so any row is reprocessable without re-scraping). **Unique `(listing_id, scrape_date)`** — this is what makes same-day re-runs idempotent (upsert, not insert). Never updated/deleted in place per design. 162 rows (3 calendar days × 54 listings).

### 3.6 `category_observations`
Per store × ECOICOP class × day aggregate stats from the *dynamic* category crawl (distinct from the fixed-basket snapshots above). `id bigserial PK`, `store_id`, `category_id`, `scrape_date`, `n_products int`, `median/mean/p25/p75_price_per_unit numeric(10,4)`, `raw_payload jsonb`. **Unique `(store_id, category_id, scrape_date)`**. 99 rows. Feeds the not-yet-built category-average index.

### 3.7 `inflation_metrics` — computed output
`id bigserial PK`, `as_of_date date`, `index_family text` (check: `fixed_basket | category_avg` — only `fixed_basket` is ever written today), `period text` (check: `daily | weekly | monthly | yearly`), `dimension text` (check: `overall | category | subcategory | store | brand` — `subcategory`/`brand` are schema-reserved, unused today), `dimension_value text` (e.g. `ALL`, an ECOICOP code, or a store slug), `price_basis text` (check: `headline | effective`), `index_value numeric(10,4)`, `inflation_rate numeric(8,4)` (nullable — only filled once a lookback-period row exists), `n_products int`, `coverage numeric(5,4)`, `computed_at timestamptz`. **Unique `(as_of_date, index_family, period, dimension, dimension_value, price_basis)`**. 360 rows (3 days × 120 rows/day: (11 categories + 1 overall + 3 stores) × 2 price bases × 4 periods = 120).

### 3.8 `scrape_runs` — observability, drives alerting
`id bigserial PK`, `started_at`/`finished_at timestamptz`, `store_id → stores.id`, `mode text` (check: `basket | category`), `listings_attempted/ok/failed int`, `status text` (check: `success | partial | failed`, default `success`), `coverage numeric(5,4)`, `error_summary text` (first 5 error reasons, semicolon-joined), `alerted bool default false` (dedup flag — set once a Telegram alert has fired for this run, so nothing re-alerts on it). 49 rows so far; **4 historical runs have been `failed`/`partial`** with coverage as low as 0.0–0.83 (from development/verification, not current steady-state — today's runs are all `success`, coverage 100%).

### 3.9 `hicp_weights_cache`
Audit snapshot of every Eurostat fetch — append-only, never deduplicated. `id bigserial PK`, `ecoicop2_code`, `weight_year smallint`, `weight numeric(8,4)`, `fetched_at`, `source_dataset default 'prc_hicp_inw'`. 1398 rows — this is large because Eurostat's `prc_hicp_inw` response includes *every* PT COICOP code (hundreds), not just the 11 we've seeded; all of them get cached for audit purposes, only the 11 matching `categories.ecoicop2_code` actually get their weight copied into `categories`.

### 3.10 `fuel_prices` — independent subsystem (migration `0004`)
`id bigserial PK`, `fuel_type text` (check: `gasoline_95 | diesel | lpg_auto`), `scrape_date date`, `price numeric(6,3)`, `unit default 'EUR/L'`, `source default 'dgeg_national_average'`, `raw_payload jsonb`, `fetched_at timestamptz`. **Unique `(fuel_type, scrape_date)`**. Deliberately has *no* foreign key into `stores`/`products` — a national average isn't a store-specific retail listing. 6 rows (2 days × 3 fuel types).

### Entity-relationship summary

```
stores ──┬──< product_listings >──┬── products ──> categories
         │                        │                    │
         └──< scrape_runs         └──< price_snapshots  └── hicp_weights_cache (audit, code-keyed only)
         │
         └──< category_observations >── categories

inflation_metrics — no FKs; keyed by (date, family, period, dimension, dimension_value, price_basis) tuples
fuel_prices — fully standalone, no FKs
```

### Connection details
- **Access method**: `supabase-py` (PostgREST over HTTPS) exclusively — no raw `psycopg2`/connection-string/pooler usage anywhere in the codebase. Every script (`scraper/db.py:SupabaseWriter`, `fuel/db.py`, `metrics/compute.py`, `weights/eurostat.py`, `seed/load_seed.py`) authenticates with `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (the **service role key**, which bypasses Row Level Security entirely).
- **No RLS policies exist in any migration file.** This has been a non-issue so far because the only client ever used is the service key, running in trusted contexts (GitHub Actions, local dev) — never a browser. This *becomes* a real design decision the moment Phase 3 exists (see §9 Security).
- Credentials live in `.env` locally (confirmed gitignored) and as GitHub Actions repo secrets (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`) — never committed.

---

## 4. Pipelines in detail

### 4.1 `scrape.yml` — daily basket + category ingest
- Matrix job, `fail-fast: false`, one job per store (`continente`, `pingo-doce`, `auchan`), each running two sequential steps: `scraper.run --mode basket` then `--mode category`.
- `concurrency: {group: scrape, cancel-in-progress: false}` — a still-running scrape blocks (doesn't cancel) the next scheduled trigger.
- Cron `"0 6 * * *"` is UTC-fixed; Lisbon's actual local run time drifts ±1h across the DST transition (accepted trade-off, documented in the workflow file — no seasonal cron split).
- **No `timeout-minutes` set on the job** — see §8 Bottlenecks.

### 4.2 `compute.yml` — daily index compute
- Single job, triggered by `workflow_run` on `scrape`'s completion (any conclusion — not gated on success, so a partial scrape still triggers a compute pass over whatever did land) plus manual dispatch.
- Runs `python -m metrics.compute`, which as of the most recent commit (`8d25d9d`) alerts via the same Telegram notifier on a hard exception or a zero-row result.
- No Playwright step — this job only talks to Supabase.

### 4.3 `fuel.yml` — daily fuel scrape
- Single job, cron `"0 6 * * *"` + manual dispatch, runs `python -m fuel.run --source dgeg`.
- As of commit `dec224e`, also wired to the same Telegram notifier.
- Independent of `scrape`/`compute` — no `workflow_run` relationship either way.

### 4.4 Manual/local entrypoints
| Command | What it does |
|---|---|
| `python -m scraper.run --store <slug> --mode basket\|category [--dry-run]` | Runs one store's scrape locally; `--dry-run` just prints listing/category counts, no browser/writes |
| `python -m metrics.compute` | Computes `inflation_metrics` for "today" (Lisbon date) |
| `python -m fuel.run --source dgeg` | Scrapes DGEG fuel prices |
| `python -m weights.eurostat` | Refreshes `categories.hicp_weight` from Eurostat (intended cadence: yearly — **not currently scheduled by any workflow**, run by hand) |
| `python -m seed.load_seed` | Idempotent upsert of stores/categories/products/listings from config + CSVs |
| `pytest` | 47 tests, all pure-function/unit-level (no live network/browser in CI) |

**Gap worth flagging**: `weights/eurostat.py` has no scheduled workflow at all. The spec calls for yearly refresh; right now that only happens if someone remembers to run it by hand.

---

## 5. Scripts and modules — what each one does

### `scraper/` — grocery store scraping
- **`store_config.py`** — loads a store's scrape parameters (`StoreConfig`) from `config/stores.yaml`; picks one random user-agent per session (not per request).
- **`antibot.py`** — the shared resilience layer: `RobotsChecker` (wraps `urllib.robotparser`), `jittered_delay`/`sleep_jitter` (2–5s + occasional 5–15s long pause), `detect_block` (keyword heuristic on page text — `"captcha"`, `"unusual traffic"`, etc.), `apply_stealth` (injects a `navigator.webdriver` override + fake plugins/languages init script), `with_backoff` (exponential backoff honoring `Retry-After`, capped at 4 attempts, never retries a `BlockDetected`).
- **`models.py`** — shared dataclasses (`Listing`, `ScrapedPrice`, `CategoryStats`, `RunResult`) and exceptions (`BlockDetected`, `FetchFailed`).
- **`db.py`** — `SupabaseWriter`: every read/write the scraper needs (`get_active_listings`, `listing_already_captured_today`, `upsert_snapshot`, `start_run`/`finish_run`/`mark_alerted`, category-observation equivalents). Also owns `lisbon_scrape_date()` — pins every date to `Europe/Lisbon` via `zoneinfo`, independent of the host machine's system timezone (this was a real production bug, fixed early on).
- **`base.py`** — `BaseScraper`: the shared basket-scrape orchestration loop (robots check → per-listing idempotent-skip → backoff-wrapped fetch → snapshot upsert → jittered delay), coverage/status computation, and Telegram alert trigger (`status in (partial, failed)` or `coverage < 0.85` or blocked).
- **`category_base.py`** — `CategoryCrawlerBase`: same shape as `base.py` but for category crawls; computes `CategoryStats` (median/mean/p25/p75) via `statistics.quantiles`, requires ≥5 products found or the category counts as failed (doesn't abort the whole crawl — one bad category is isolated).
- **`continente.py` / `pingodoce.py` / `auchan.py`** — one concrete scraper per store, each implementing `fetch_listing`. All three are **DOM-primary** (not JSON-LD-primary, despite the general spec preference) because each site's DOM exposes the promo/regular price pair and price-per-unit that JSON-LD lacks. Continente additionally falls back to JSON-LD if the DOM selectors miss. Notable per-store quirks:
  - *Continente*: price split across adjacent DOM nodes, tolerant regex; `parse_price_per_unit` handles `"€/lt"`, `"€/kg"`, `"€/doz"`, etc.
  - *Pingo Doce*: **no EAN exposed anywhere** on the page (cross-store matches rely on `match_method='manual'` curation); `parse_unit_measure` has a weight-only fallback (`fallback_price / weight`) for fresh/counter items (butcher, cheese) that show only a bare weight instead of an embedded price-per-unit — a real bug found and fixed mid-project.
  - *Auchan*: cleanest EAN exposure of the three (JSON-LD `gtin` + `data-ean` attribute + visible text, redundantly). Its promo/regular-price selector (`.auc-price__list .value`) is **inferred, not confirmed against a live promo'd product** — flagged in the module docstring as needing verification once one is observed.
- **`continente_category.py` / `pingodoce_category.py` / `auchan_category.py`** — category-listing crawlers. Continente/Auchan crawl directly-curated category URLs (allowed by robots.txt). Pingo Doce instead enumerates its ~15,600-URL product sitemap and filters by `path_prefix`/`keywords`/`exclude_keywords` per category (its own category navigation is entirely disallowed `cgid` search URLs) — sitemap fetch is cached once per crawler-instance run to avoid 11 redundant multi-MB refetches.
- **`run.py`** — CLI entrypoint wiring config → scraper/crawler class → `SupabaseWriter` → `TelegramNotifier`/`ConsoleNotifier` fallback. Used by both local dev and `scrape.yml`.

### `weights/eurostat.py`
Fetches Portugal's HICP item weights from Eurostat's `prc_hicp_inw` dataset (JSON-stat v2 format), parses the flat multi-dimensional `value` map by computing dimension strides by hand, extracts only the latest available year, converts Eurostat's compact codes (`CP01113`) to dotted ECOICOP notation (`01.1.1.3`) via `to_dotted_ecoicop`, appends every fetched record to `hicp_weights_cache` (audit), and updates `categories.hicp_weight` only for codes that are already seeded.

### `metrics/`
- **`formulas.py`** — pure math, no I/O: `jevons_class_index` (weighted geometric mean of price relatives, weights renormalized to sum to 1 inside the call), `weighted_overall_index` (weighted arithmetic mean across classes, same renormalization), `inflation_rate` (`(current/base − 1) × 100`).
- **`compute.py`** — orchestrates the daily compute: fetches all active `product_listings` (optionally scoped to one store), fetches every snapshot for those listings, computes each listing's relative (`current_price / its_own_first_ever_price` — so a product added later still gets a valid relative from its own start date, not a missing/zero base), groups into per-ECOICOP-class Jevons indices, combines into an `overall` row (all stores) and a `store` row (per store), for both `headline`/`effective` price bases and all 4 periods, upserting 120 rows/day. `inflation_rate` is populated only when a same-scope row already exists at the lookback date (`as_of_date - {1,7,30,365} days`) — so weekly/monthly/yearly rates silently start appearing on their own once enough history exists, no code change needed.

### `fuel/`
- **`dgeg.py`** — scrapes DGEG's public "Preço Médio Diário" page via Playwright (select fuel type, click search, regex-parse the resulting HTML table row-by-row: `ROW_RE`). No `robots.txt` exists on this subdomain (both a plain request and a browser navigation time out — no route configured), so the usual `RobotsChecker` is skipped; the page's own footer text (explicitly free for non-commercial use) is the operative permission instead.
- **`db.py`** — `upsert_fuel_price`, independent of `scraper.db.SupabaseWriter` (no store/listing concept applies).
- **`run.py`** — CLI entrypoint; as of the latest commit, builds the same Telegram/console notifier scraper/run.py does and alerts on total failure (`no fuel prices retrieved`) or partial failure (`< 3` fuel types returned). No `scrape_runs`-equivalent table exists for fuel, so there's no `alerted` dedup — every failing run sends its own alert.

### `alerting/`
- **`base.py`** — `Notifier` ABC, one method: `async def send(message: str)`.
- **`telegram.py`** — `TelegramNotifier`, a plain `httpx` POST to the Telegram Bot API (`sendMessage`, Markdown parse mode). No SDK dependency.
- **`console.py`** — `ConsoleNotifier`, prints to stderr; used automatically whenever `TELEGRAM_TOKEN`/`TELEGRAM_CHAT_ID` aren't set (local dev without credentials) — never used by the scheduled Actions, which always have the secrets.

### `seed/`
- **`load_seed.py`** — idempotent orchestrator: `stores` (from YAML) → `categories` (hardcoded list, weights populated separately) → `products`/`product_listings` (from the two CSVs, resolving `product_key` → `product_id` so shared EANs collapse onto one product row across stores).
- **`categories.py`** / **`stores.py`** — the seed data for those two tables.
- **`products.csv`** / **`listings.csv`** — the actual basket definition; see `seed/README.md` for the full curation history and known pitfalls (canonical-name exact-match requirement, stale/delisted URLs redirecting to homepage instead of 404ing).

### `config/`
- **`stores.yaml`** — per-store scrape parameters (user-agent pool, delay range, locale/timezone, active flag).
- **`category_urls.yaml`** — per-store, per-ECOICOP-code category discovery config (direct URL list for Continente/Auchan; `path_prefix`/`keywords`/`exclude_keywords` for Pingo Doce's sitemap-filtering approach).

---

## 6. Methodology (as implemented)

Mirrors the HICP elementary-aggregate approach, implemented as plain Python (`metrics/`) rather than SQL views — a deliberate, documented deviation from the spec's stated general preference for "computation lives in SQL," made because the per-listing base-date lookup and gap-handling logic (§6 below) were more legible as ordinary Python than as window-function SQL.

1. **Elementary relative**, per listing: `price_i,t / price_i,0`, where `price_i,0` is *that listing's own first-ever snapshot date* — not a fixed global day-0. This means a product added to the basket later still gets a meaningful relative starting from its own first day, rather than a missing/undefined value.
2. **Per ECOICOP class**: Jevons (weighted geometric mean) of elementary relatives, `within_cat_weight`-weighted, renormalized to sum to 1 within whatever's actually covered that day.
3. **Overall / per-store index**: weighted arithmetic mean of class indices, weighted by `hicp_weight`, again renormalized within the covered subset — this is what makes the index a "supermarket HICP-comparable" index rather than the full HICP (only COICOP divisions 01, 02.1, 05.6.1[dropped], 12.1.x are covered).
4. **Inflation rate**: `(index_t / index_{t−P} − 1) × 100`, only populated once a same-scope `inflation_metrics` row already exists at `t−P`.
5. Both **headline** (`regular_price`) and **effective** (`price`) bases are computed in parallel for every scope — the gap between them is the promo-intensity signal called for in the spec.
6. **Missing-data handling**: a listing with no snapshot for `as_of_date` is simply excluded from that day's `n_products`/`coverage` for its scope (not carried forward as a stale price the way the spec originally described — current code drops it entirely rather than reusing the last observed price). *This is a small, real divergence from the spec's stated gap-handling method ("missing product → carry last observed price forward") worth being aware of if reconciling against the spec text.*

---

## 7. Expected day-to-day behavior

1. **06:00 UTC** (approx.; drifts ±1h across DST): `scrape.yml` and `fuel.yml` fire in parallel. Each of the 3 grocery stores runs its basket scrape then its category crawl, sequentially, within its own matrix job — genuinely parallel *across* stores, never parallel *within* a store (spec §7's "1 tab per store, stores in parallel at most").
2. Each listing/category already captured for today's Lisbon calendar date is skipped (idempotent same-day cache) — safe to re-run any workflow manually without creating duplicate rows (upsert on the relevant unique constraint).
3. On `scrape.yml`'s completion (any conclusion), `compute.yml` fires and (re)computes all 120 `inflation_metrics` rows for today — this makes a manual re-run of `compute.yml` always safe too (idempotent upsert on `(as_of_date, index_family, period, dimension, dimension_value, price_basis)`).
4. `index_value = 100` from day 1 for every listing/scope (base = its own start date). Daily `inflation_rate` starts appearing after 2 days of history; weekly after 7; monthly after 30; yearly after 365 — no code change needed at any of those milestones, it's purely a function of how much history exists.
5. Coverage is currently 100% across all three stores on every recent run — no missing products, no low-coverage alerts firing in steady-state.

---

## 8. Alerts and safeguards actually implemented

| Trigger | Where | Channel |
|---|---|---|
| Scrape run `status` = `partial`/`failed`, OR `coverage < 0.85`, OR CAPTCHA/block detected | `scraper/base.py:_alert` | Telegram (falls back to console print if secrets absent) |
| Category crawl `status` = `partial`/`failed`, OR `coverage < 0.85` | `scraper/category_base.py:_alert` | Telegram |
| Compute job raises an exception, or writes zero rows | `metrics/compute.py:main` | Telegram |
| Fuel scrape retrieves 0 fuel types (total failure) or < 3 (partial) | `fuel/run.py:main` | Telegram |
| Unexpected per-listing error during a basket scrape (Playwright timeout, DB write failure, etc.) | `scraper/base.py` (catch-all, mirrors `category_base.py`) | Telegram — bucketed into that run's `error_summary`, tagged `"unexpected error"` |
| `start_run()` fails to write to `scrape_runs` (DB unreachable at run start) | `scraper/base.py`/`category_base.py` | Telegram (`"FAILED TO START — database unreachable?"`), then re-raises so the Action step still fails |
| `finish_run()` fails to write to `scrape_runs` (DB unreachable at run end) | `scraper/base.py`/`category_base.py` | Telegram (alert still fires, tagged `"DB write failed while finishing this run"`), then re-raises |
| Fuel per-fuel-type DB write fails | `fuel/run.py:main` | Telegram, merged with any missing-fuel-type message |
| Any unhandled exception in any workflow step | N/A (script-level failure) | GitHub Actions' native failure email (zero-config backup, spec §8) |
| `scrape_runs.alerted` | `SupabaseWriter.mark_alerted` | Prevents duplicate Telegram alerts for the same incident (grocery scrapers only — fuel has no equivalent table/flag); a failure to set this flag itself is now swallowed as best-effort rather than losing the alert that already sent |

As of commit `2069911`, a database problem is distinguishable from a source/site problem in the alert text itself (`"DB write failed"` / `"FAILED TO START"` wording) rather than only surfacing as a bare GitHub Actions failure email — this closed a real gap where an unexpected exception (not just the anticipated `BlockDetected`/`FetchFailed` cases) would previously propagate straight out of `run()`, skipping `finish_run()` and the alert entirely.

**Still not implemented** (present in the spec, not in code):
- "A canonical product missing ≥3 consecutive days" — no query currently checks for this; a listing could silently go stale (last snapshot weeks old) without triggering anything, as long as its *daily* coverage percentage stays above 0.85 overall (a single missing listing out of 12–20 per store often doesn't cross that threshold).
- Fuel has no `scrape_runs`-equivalent observability table at all — no historical run log to query, only whatever landed (or didn't) in `fuel_prices` plus whatever Telegram alert fired at the time.
- Eurostat weight refresh has no failure alerting (it's not on any schedule at all yet — see §4.4).

Anti-bot / respectful-scraping safeguards actually in place: persistent Playwright browser context per store, `navigator.webdriver`/plugins/languages stealth patch, per-session (not per-request) random user-agent, `robots.txt` + `Crawl-delay` respected via `RobotsChecker`, jittered 2–5s delays (+ occasional 5–15s long pause), exponential backoff honoring `Retry-After` on 403/429/5xx (capped at 4 attempts), explicit CAPTCHA/block-page text detection that halts the run rather than looping, `PROXY_URL` env var support (unused/off by default).

---

## 9. Limitations arising from each external party, and mitigations

### The three grocery retailers (Continente, Pingo Doce, Auchan)
- **Selector/DOM drift**: every price extraction depends on hand-verified CSS selectors against a snapshot-in-time of each site's markup. A redesign silently breaks extraction — the code fails loudly (`FetchFailed`, alerted via Telegram) rather than writing garbage, which is the right failure mode, but there's no automated detection *before* it happens.
  - *Mitigation in place*: Continente falls back to JSON-LD if DOM selectors miss. *Further mitigation to consider*: a lightweight canary check (e.g. assert a known product's price is within a plausible range) would catch silent selector drift faster than waiting for coverage to visibly drop.
- **Unverified selectors**: Auchan's promo-price selector is explicitly flagged in code as inferred, not confirmed against a real live promotion. It will either work correctly or silently mis-attribute promo status the first time a real Auchan promo is scraped — worth a deliberate spot-check rather than waiting to discover it accidentally.
- **IP-based blocking**: GitHub Actions runners share IP ranges across all GitHub customers; a retailer's anti-bot vendor (Akamai/Cloudflare/etc.) could block that range independent of anything this project does. `PROXY_URL` exists as an escape hatch but is unused.
- **Inconsistent EAN exposure**: Pingo Doce exposes no EAN at all, forcing manual cross-store matching for its listings (more curation labor, more human-error surface than the EAN-matched stores).
- **Stale/delisted URLs**: already observed — some sitemap-sourced Continente URLs 200-redirect to the homepage instead of 404ing, silently returning no `Product` JSON-LD. Mitigation already adopted: always verify JSON-LD `@type == "Product"`, not just HTTP status, during curation.
- **Terms-of-service risk**: scraping is inherently in tension with most retailers' ToS regardless of how respectfully it's done (rate limits, stealth patches, robots.txt compliance don't make it explicitly *authorized*). This is a standing legal/reputational exposure, not a bug — worth keeping scraping volume low and non-disruptive as the basket grows, and revisiting if this project's scope or visibility changes materially.

### GitHub Actions
- **No job-level timeout set** on any of the 3 workflows — see §10 (Bottlenecks) for why this matters.
- **Ephemeral runners**: every run is a fresh VM. The Playwright "persistent browser context" (`launch_persistent_context`, meant to build up trust/cookies over time per the anti-bot design) **never actually persists across scheduled CI runs** — only within a single run, and locally across manual runs on the same machine. This undermines part of the intended anti-bot benefit; see §11 (Inefficiencies).
- **Cron drift**: fixed-UTC cron means the *actual* Lisbon-local run time shifts ±1h across DST transitions twice a year (accepted trade-off, not a bug).
- **`workflow_run` coupling**: `compute.yml` depends on `scrape.yml`'s workflow-level completion event; if `scrape.yml` itself fails to trigger (e.g., YAML syntax error, GitHub platform incident), `compute.yml` never fires either, with no independent fallback cron.
- **Actions cache service outages**: already observed once in practice (`Failed to save/restore: cache service responded with 400`) — non-fatal (falls back to a fresh dependency install), just slower.

### Supabase
- **Service-role key bypasses RLS entirely** — see §12 (Security).
- **Free/shared-tier considerations** (not confirmed which tier this project is on, but worth checking): Supabase free-tier projects can pause after a period of inactivity, and have bandwidth/row caps. Given daily automated traffic this is unlikely to trigger a pause, but a plan-tier check is worth doing before this becomes something people depend on daily.
- **PostgREST semantics**: every write is a small, independent HTTP round-trip (`.upsert().execute()`) — correct, but see §10 for the scaling implication.

### Eurostat (`prc_hicp_inw`)
- **Annual cadence, real lag**: HICP weights are only updated once a year by Eurostat itself; this project's own refresh isn't scheduled at all currently (manual-only), compounding the staleness risk.
- **Schema fragility**: the JSON-stat v2 parser (`weights/eurostat.py:parse_response`) manually computes dimension strides from `raw["size"]`/`raw["id"]` ordering — if Eurostat ever changes dimension ordering or the response shape, this breaks with no fixture-based canary beyond the unit tests (which use a saved fixture, so they wouldn't catch a real API change either).
- No SLA/uptime guarantee on a public statistical API — acceptable for a yearly-cadence job, but there's currently no alert if a manual run fails.

### DGEG (fuel data)
- **No formal API, no robots.txt** — the operative permission is the page's own footer text (non-commercial use only). This is a legal constraint, not just a technical one: if this project ever became commercial, this data source's basis would need revisiting.
- **Reporting lag**: `scrape_date` is DGEG's own most-recently-finalized date, which can lag the actual scrape day by 1–2 days — this is already correctly *not* forced into the Lisbon "today" convention the grocery pipeline uses, but it does mean naive date-alignment between `fuel_prices` and `price_snapshots` isn't safe without accounting for the offset.
- **Page-structure fragility**: `ROW_RE`'s regex parsing of the results table is exact-format-dependent, same class of risk as the grocery DOM selectors.
- **National average only**: masks brand-level variation entirely (explicitly scoped as a first prototype — per-brand comparison is documented future work).

### Telegram
- **Single chat_id, single bot token, no secondary channel** — if the bot token is revoked/rate-limited, or the one configured chat becomes unreachable, the *only* remaining signal is GitHub Actions' native failure email, which only fires on an unhandled exception, not on the "soft" failure modes (partial/low-coverage) this project cares most about.
- **No alert deduplication for fuel** (no `scrape_runs`-equivalent table) — a persistently failing fuel scrape would send one Telegram message every single day rather than once per incident.

### Playwright / Chromium
- **Version drift**: `playwright>=1.45` (open-ended in `pyproject.toml`) means a future `uv sync` could pull a newer Playwright/Chromium than what the stealth patches and selectors were verified against — a real (if usually small) compatibility risk each time dependencies are refreshed.
- **Anti-bot arms race**: stealth patches here are a fixed, auditable snapshot (`navigator.webdriver`, plugins, languages) — increasingly sophisticated fingerprinting (canvas/WebGL fingerprinting, TLS fingerprinting, behavioral analysis) isn't addressed and isn't easily addressable from Playwright alone.

---

## 10. Bottlenecks

- **No `timeout-minutes` on any workflow job.** GitHub's default cap is 360 minutes (6 hours) per job. A single hung `page.goto(..., wait_until="networkidle")` call (a real risk — "networkidle" can wait indefinitely on a page with long-polling/analytics scripts) could occupy the `scrape`/`fuel` concurrency slot for hours, delaying or entirely skipping the next scheduled trigger (since `cancel-in-progress: false` queues rather than cancels).
- **Fully sequential, deliberately slow scraping within a store**: one tab, one listing at a time, 2–5s (+occasional 5–15s) jittered delay between each — by design (anti-bot posture), but it means basket-scrape wall-clock time scales linearly with listing count. At 12–20 listings/store today this is a few minutes; at a few hundred (a plausible future basket size) this becomes tens of minutes per store, still within Action limits but worth watching.
- **Pingo Doce's category crawl** is the most request-heavy path of the three stores: it visits up to 15 individual product pages per category (`SAMPLE_CAP`) across 11 categories, on top of its ~15,600-URL sitemap fetch (now cached once per run, previously refetched per category) and its 12 fixed-basket listings — meaningfully more total requests per day than either Continente or Auchan's direct category-page crawl (which loads one listing page per category, not N individual product pages).
- **`workflow_run` chain latency**: `compute.yml` only starts after `scrape.yml`'s *entire* matrix (all 3 stores) reports completion — a single slow/stuck store job delays compute for all stores' data, not just its own.
- **Eurostat weight fetch has no incremental/conditional-GET logic** — it always pulls the full PT dataset (hundreds of COICOP codes) even though only 11 are used; harmless at yearly cadence, would matter if this were ever run more frequently.

---

## 11. Inefficiencies

- **Persistent browser context doesn't actually persist in CI.** `launch_persistent_context` writes to `.pw-profile/<store>` — a real, meaningful anti-bot mechanism for local dev (cookies/session trust accumulate run to run), but GitHub Actions runners are stateless VMs and no workflow caches `.pw-profile/` via `actions/cache`, so in production this directory is created fresh and discarded every single day. The code isn't wrong, but the intended benefit (trust accumulation) is currently only realized locally, not in the actual daily production runs.
- **Triplicated notifier-selection boilerplate.** The identical "build a `TelegramNotifier`, fall back to `ConsoleNotifier` if secrets are missing, print a warning" block is copy-pasted verbatim in `scraper/run.py`, `fuel/run.py`, and `metrics/compute.py`. Harmless today (each is ~10 lines), but it's the kind of duplication that will drift if the alerting logic ever needs to change (e.g., adding a Discord fallback) — a shared `alerting/build.py:build_notifier()` helper would be a natural, low-risk consolidation whenever one of these files is touched next.
- **Redundant query pattern in `metrics/compute.py`.** `compute_metrics_for_date` first fetches *all* active listings across every store (the "overall" scope), then loops over each store and fetches that store's listings again (a strict subset) for the "store" scope — meaning every store's listing rows are effectively fetched twice per run. At 54 listings this costs a handful of extra PostgREST round-trips; would be worth caching/reusing the per-store subset from the first fetch if the basket grows substantially.
- **No batched writes.** Every snapshot upsert, every `inflation_metrics` row, every category observation is its own `.execute()` call rather than a single batched multi-row upsert per table per run. PostgREST supports multi-row upserts (already used for `hicp_weights_cache` cache inserts and `seed_categories`) — the scraper and compute paths could adopt the same pattern to cut round-trips substantially as data volume grows.
- **`hicp_weights_cache` accumulates ~1,400 rows per fetch**, almost all for COICOP codes this project doesn't use — intentional (audit completeness), but worth being aware of as a quietly-growing table with no retention/pruning policy.

---

## 12. Security and vulnerable points to pay attention to

- **`SUPABASE_SERVICE_KEY` is a full-access, RLS-bypassing credential**, held in GitHub Actions secrets and local `.env`. It is the single highest-value secret in this system — anyone who obtains it can read or write every table, including deleting `price_snapshots` history (the append-only guarantee is enforced by convention/code discipline, not by a database-level permission that would stop a holder of this key from doing it anyway). Recommend: rotate it if there's ever any doubt it was exposed, and keep it out of logs (none of the current scripts print it, which is correct — keep that invariant as code changes).
- **Credentials were shared in plaintext through this chat session** during initial setup. `.env` itself is correctly gitignored and was never committed, but the literal key values now also exist in this conversation's own transcript/logs, which is a distinct exposure surface from "is it in git." Worth rotating the Supabase service key and Telegram bot token at some point as a hygiene measure, independent of any specific incident, precisely because they've been pasted in plaintext at least once.
- **No Row Level Security policies exist at all.** Currently irrelevant (only the trusted service key is ever used, never a browser-facing anon key), but this is a decision to revisit deliberately, not by default, once Phase 3 exists — a public FastAPI/Next.js app must either (a) go through a backend that itself holds the service key and only exposes curated read-only endpoints (recommended), or (b) use a scoped anon key with explicit RLS read-only policies restricted to non-sensitive tables. Shipping Phase 3 against the service key directly, or without RLS, would expose full write access to anyone who inspects the frontend's network requests.
- **No job-level timeouts (§10) is also a minor availability/security-adjacent gap** — a hung job holding a concurrency slot for up to 6 hours is a (low-severity, self-inflicted) denial-of-service against the project's own pipeline.
- **Supply-chain exposure via CI dependency installation.** Every workflow run does `uv sync --frozen` (good — pinned via `uv.lock`) and `playwright install --with-deps chromium`; a compromised transitive PyPI package would execute with access to the run's secrets (`SUPABASE_SERVICE_KEY`, `TELEGRAM_TOKEN`). `--frozen` meaningfully limits this to "whatever was already in the lockfile," but the lockfile itself should get periodic review/update (e.g. via Dependabot) rather than staying static indefinitely, since "frozen" doesn't mean "audited."
- **DGEG scraping's legal basis is a footer disclaimer, not a formal agreement** — low risk at current (non-commercial, low-traffic) scope, but explicitly noted as something that would need re-evaluating if the project's use case changes (see §9).
- **General ToS-tension of scraping three retailers' sites** is a standing, non-technical risk category worth keeping in mind as basket size / request volume grows — nothing to "fix" per se, but worth not losing sight of as a design constraint (keep concurrency at 1 tab/store, keep delays realistic, don't chase aggressive coverage at the cost of load).
- **`raw_payload jsonb` blobs** store full scrape evidence (selector text, HTML fragments) — for product catalogue pages this is very unlikely to contain anything sensitive, but it's worth a mental note if any future data source's raw payload could carry PII, since these blobs are never redacted before storage.

---

## 13. Current state at a glance (as of 2026-07-06)

| Table | Rows |
|---|---|
| stores | 4 (3 active) |
| categories | 11 |
| products | 44 |
| product_listings | 54 |
| price_snapshots | 162 (3 days × 54) |
| category_observations | 99 |
| inflation_metrics | 360 (3 days × 120) |
| scrape_runs | 49 |
| hicp_weights_cache | 1,398 |
| fuel_prices | 6 (2 days × 3) |

Test suite: 47 tests, all pure-function/unit-level, no live network dependency, all passing.

Phases per the build spec: **Phase 1 (foundation + multi-store ingest) — done.** **Phase 2 (metrics + dynamic crawl) — mostly done**: fixed-basket compute is built, scheduled, and alerting; the *category-average* index (reading from `category_observations` into a `category_avg` row in `inflation_metrics`) is not yet built, only its data collection is. **Phase 3 (web app) — not started.**

---

## 14. Open items worth deciding on before/alongside Phase 3

- Category-average index compute (the other half of Phase 2, per the spec's "two index families in parallel" decision).
- Missing-product ≥3-day alert, and a `scrape_runs`-equivalent observability table for fuel.
- Job-level `timeout-minutes` on all three workflows.
- A decision on Phase 3's data-access pattern (backend-holds-service-key vs. scoped anon key + RLS) — see §12.
- Scheduling `weights/eurostat.py` (currently manual-only).
- Auchan promo-selector verification against a real live promotion.
