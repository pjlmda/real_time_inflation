# Portugal Real-Time Inflation Tracker — Project Plan (v2)

> A daily-updating inflation index for Portugal, built from online supermarket
> price data, methodologically aligned with INE / Eurostat HICP so the numbers
> are comparable to official figures. This document is the build spec — hand it
> to Claude Code as the source of truth and implement phase by phase.

---

## 0. Confirmed decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Stores | **Multiple from day one:** Continente, Pingo Doce, Auchan, Lidl (config-driven; more can be added) |
| 2 | Basket | **Aligned to ECOICOP v2 (UN COICOP 2018)** so it's comparable to INE/Eurostat HICP |
| 3 | Fixed vs dynamic | **Both** — a fixed comparable basket index *and* a dynamic category-average index |
| 4 | Price bases | **Both** — headline (regular price) and effective (displayed/promo price) |
| 5 | Surface | **Simple web app** (Next.js) after the data layer works → Phase 3 in scope |
| 6 | History | **Accrues from day 1**; long-period rates appear only once history exists |
| 7 | Anti-bot | **Required** — resilient, respectful scraping (see §7) |
| 8 | Alerting | **Required** — warn on any retrieval failure or low coverage (see §8) |

### Classification note (important — verified Jan 2026)
- HICP now uses **ECOICOP version 2**, identical to **UN COICOP 2018** to 5-digit level.
- Index reference period is now **2025 = 100**.
- **Weights** for Portugal are published yearly in Eurostat dataset **`prc_hicp_inw`**
  (HICP item weights) and should be **fetched programmatically** from the Eurostat
  dissemination API, country `PT`, latest year — never hardcoded. This is what makes
  the tracker comparable and self-updating each year.

---

## 1. Goal

Every day, produce a defensible grocery-inflation measurement for Portugal, broken
down by:

- **Periods:** daily, weekly (7d), monthly (30d), yearly (365d) — each emitted only
  when enough history exists.
- **Dimensions:** overall, per ECOICOP category & subcategory, per store, per brand.
- **Two index families:** the **fixed-basket index** (primary, comparable to HICP)
  and the **dynamic category-average index** (robustness / self-healing).
- **Two price bases:** headline (regular) and effective (what shoppers pay).

The headline number must be explainable and auditable — same methodology family as
Eurostat HICP (geometric-mean elementary aggregates, COICOP weights).

---

## 2. Architecture

```
   daily 06:00 Lisbon   ┌────────────────────────────────┐
   GitHub Actions ──────▶│ Scraper (Python + Playwright)   │
                         │  • fixed-basket URLs (per store)│
                         │  • dynamic category crawl       │
                         │  • anti-bot layer (§7)          │
                         └───────────────┬─────────────────┘
                          upsert raw      │   on failure / low coverage
                          snapshots       │        │
                                          ▼        ▼
                         ┌────────────────────┐  ┌──────────────────┐
                         │ Supabase Postgres   │  │ Alerter (§8)      │
                         │ raw + dimensions    │  │ Telegram/Discord  │
                         └─────────┬──────────┘  └──────────────────┘
                          07:00     │ compute
                                    ▼
                         ┌────────────────────┐
                         │ Metrics builder     │  ← weights from Eurostat API
                         │ indices + rates     │
                         └─────────┬──────────┘
                                   ▼
                    ┌──────────┐      ┌──────────────────┐
                    │ FastAPI   │─────▶│ Next.js web app   │ (Phase 3)
                    │ Render/Rwy│      │ Vercel            │
                    └──────────┘      └──────────────────┘
```

Reuses the existing S&P-platform stack. No new paid vendors required.

---

## 3. Tech stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Scraping | **Playwright (Python)** + stealth patches | JS-rendered sites; see §7 |
| Parsing | embedded JSON first, then `parsel`/`selectolax` | prefer structured data over DOM |
| DB | **Supabase Postgres** | free tier ample (see §10) |
| Compute | SQL views + thin Python orchestrator | keep math in SQL for auditability |
| Weights | Eurostat dissemination REST API (`prc_hicp_inw`) | fetched yearly, cached in DB |
| API | **FastAPI** (Render/Railway) | read-only |
| Frontend | **Next.js / Vercel** | Phase 3 |
| Scheduler | **GitHub Actions cron** | scrape + compute workflows |
| Alerts | Telegram bot **or** Discord webhook | free; + Actions native failure email |

---

## 4. Data model (PostgreSQL / Supabase)

Fixed-first, dynamic-ready, multi-store from day one. `price_snapshots` is
append-only — that's what makes the index auditable.

### 4.1 `stores`
`id` smallserial PK · `name` · `slug` unique · `base_url` · `robots_checked_at` timestamptz · `country` default 'PT'

### 4.2 `categories`  (ECOICOP v2 hierarchy)
| column | type | notes |
|--------|------|-------|
| id | smallserial PK | |
| ecoicop2_code | text | e.g. `01.1.1` (bread & cereals), 5-digit at leaf |
| name_pt / name_en | text | |
| parent_id | smallint FK self | null = division |
| level | smallint | 2=division … 5=class |
| hicp_weight | numeric(7,4) | from `prc_hicp_inw`, PT, latest year; leaf level |
| weight_year | smallint | which annual weight set |

### 4.3 `products`  (the fixed basket — one row per canonical good)
| column | type | notes |
|--------|------|-------|
| id | serial PK | |
| canonical_name | text | `Leite gordo UHT 1L` |
| brand | text | |
| is_store_brand | boolean | |
| category_id | smallint FK categories | ECOICOP v2 leaf class |
| ean | text | barcode — primary cross-store key |
| package_size | numeric · `package_unit` text | `1`, `L`/`kg`/`un`/`g`/`ml` |
| within_cat_weight | numeric(7,4) | default equal within class |
| is_active | boolean default true | flip false when discontinued |
| created_at | timestamptz default now() | |

### 4.4 `product_listings`  (store-specific identity — enables cross-store)
| column | type | notes |
|--------|------|-------|
| id | serial PK | |
| product_id | int FK products | |
| store_id | smallint FK stores | |
| store_sku | text · `ean` text | store id + barcode if exposed |
| url | text | page the scraper hits |
| raw_name | text | name as displayed |
| match_method | text | `ean` / `manual` / `fuzzy` |
| is_active | boolean default true | |
| UNIQUE (product_id, store_id) | | |

### 4.5 `price_snapshots`  (append-only fact table)
| column | type | notes |
|--------|------|-------|
| id | bigserial PK | |
| listing_id | int FK product_listings | |
| scrape_date | date | one row per listing per day |
| scraped_at | timestamptz | exact fetch time |
| price | numeric(8,2) | **displayed** price (effective) |
| regular_price | numeric(8,2) | base price (headline); = price if no promo |
| price_per_unit | numeric(10,4) · `unit_basis` text | normalized €/kg or €/L — **critical** |
| is_promotion | boolean · `promotion_label` text | verbatim promo text |
| in_stock | boolean | |
| currency | text default 'EUR' | |
| raw_payload | jsonb | full scraped blob → reprocessable |
| UNIQUE (listing_id, scrape_date) | | idempotent daily upsert |

Indexes: `(listing_id, scrape_date)`, `(scrape_date)`.

### 4.6 `category_observations`  (DYNAMIC index source)
Per store × ECOICOP class × day: aggregate of *all* products found in that class
during the category crawl. Feeds the self-healing category-average index.
| column | type | notes |
|--------|------|-------|
| id | bigserial PK | |
| store_id | smallint FK · `category_id` smallint FK | |
| scrape_date | date | |
| n_products | int | how many products seen |
| median_price_per_unit | numeric(10,4) | robust central tendency |
| mean_price_per_unit | numeric(10,4) | |
| p25 / p75 price_per_unit | numeric(10,4) | distribution |
| raw_payload | jsonb | |
| UNIQUE (store_id, category_id, scrape_date) | | |

### 4.7 `inflation_metrics`  (computed output)
| column | type | notes |
|--------|------|-------|
| id | bigserial PK | |
| as_of_date | date | |
| index_family | text | `fixed_basket` / `category_avg` |
| period | text | `daily` / `weekly` / `monthly` / `yearly` |
| dimension | text | `overall` / `category` / `subcategory` / `store` / `brand` |
| dimension_value | text | id/slug or `ALL` |
| price_basis | text | `headline` / `effective` |
| index_value | numeric(10,4) | base 100 at series start |
| inflation_rate | numeric(8,4) | % change over the period |
| n_products | int · `coverage` numeric(5,4) | sample size + basket coverage |
| computed_at | timestamptz default now() | |
| UNIQUE (as_of_date, index_family, period, dimension, dimension_value, price_basis) | | |

### 4.8 `scrape_runs`  (observability — drives alerting)
`id` · `started_at`/`finished_at` · `store_id` · `mode` (`basket`/`category`) ·
`listings_attempted`/`ok`/`failed` · `status` (`success`/`partial`/`failed`) ·
`coverage` numeric · `error_summary` · `alerted` boolean.

### 4.9 `hicp_weights_cache`  (Eurostat snapshot, for audit)
`ecoicop2_code` · `weight_year` · `weight` · `fetched_at` · `source_dataset` (`prc_hicp_inw`).

---

## 5. Basket — alignment to INE / Eurostat

**Scope:** the supermarket-buyable slice of HICP:
- **01 Food and non-alcoholic beverages** (the comparable core)
- **02.1 Alcoholic beverages** (wine, beer, spirits)
- **05.6.1** household cleaning/consumables (detergents, etc.)
- **12.1.x** personal care (toiletries)

**Build steps:**
1. Pull ECOICOP v2 leaf classes + **Portugal weights** from Eurostat `prc_hicp_inw`
   (dissemination API: `https://ec.europa.eu/eurostat/api/dissemination/...`,
   filter `geo=PT`, latest `time`). Store in `hicp_weights_cache` + `categories`.
2. For each in-scope leaf class, curate **3–8 representative products** per store
   (e.g. class `01.1.4.x` milk → whole/semi/skimmed UHT 1L from each chain).
   Target ~80–120 canonical products total.
3. Because we only cover part of the full HICP, **re-normalize weights within the
   covered subset** so they sum to 1. Document this clearly — the index is a
   "supermarket HICP-comparable" index, not the full HICP.
4. Cross-store matching: match listings to canonical products by **EAN**; fall back
   to a curated manual mapping where EAN isn't exposed (`match_method` records which).

---

## 6. Inflation methodology

Mirror the **HICP elementary-aggregate** approach.

- **Elementary relative** (product *i*, day *t* vs base day 0): `price_i,t / price_i,0`
- **Per class (Jevons / geometric mean):**
  `class_index_t = ( Π_i (price_i,t / price_i,0)^{w_i} ) × 100`
  Geometric mean within the elementary aggregate is the Eurostat choice — note it.
- **Overall (weighted arithmetic of classes):**
  `overall_t = Σ_c (hicp_weight_c × class_index_c,t) / Σ_c hicp_weight_c`
- **Inflation over period P:** `(index_t / index_{t-P} − 1) × 100`, emitted only if
  `index_{t-P}` exists. Daily series: also report a **7-day moving average** as the
  headline (raw daily is noisy from rounding/promos).
- **Two bases:** run the whole stack on `regular_price` (headline) and on `price`
  (effective). The gap = promo intensity, itself a useful signal.
- **Two families:** `fixed_basket` (above) and `category_avg` (built from
  `category_observations` medians — same period math, self-healing, robustness check).

**Gaps / substitutions:**
- Missing/out-of-stock product → carry last observed price forward for continuity,
  exclude from `n_products`, lower `coverage`.
- Discontinued (`is_active=false`) → freeze last relative; log for basket upkeep.
- Any day with `coverage < 0.85` → flagged low-confidence in API + triggers an alert.

---

## 7. Anti-bot / resilient scraping (REQUIRED)

Goal: be a respectful, robust scraper of **public price data** that doesn't get
blocked by ordinary bot heuristics. Not for defeating hard security or auth.

**Browser realism (Playwright):**
- Launch persistent context per store; reuse cookies/session.
- Realistic browser fingerprint: pt-PT locale, `Europe/Lisbon` timezone, normal
  desktop viewport, real Accept-Language headers.
- Apply stealth patches (remove `navigator.webdriver`, normal `navigator.plugins`,
  WebGL/canvas not nulled). `playwright-stealth` or hand-rolled init script.
- Small rotating pool of current, real desktop user-agents.

**Behaviour:**
- **Low concurrency:** 1 tab per store, stores in parallel at most.
- **Human-like pacing:** randomized 2–5 s delays with jitter between product pages;
  occasional longer pauses. ~100 pages/store/day is gentle.
- Spread the schedule; don't hammer all URLs in a burst.

**Robustness:**
- **Respect `robots.txt`** and any `Crawl-delay`; record `robots_checked_at`.
- **Exponential backoff** on 403/429/5xx; honor `Retry-After`. Cap retries, then
  mark the listing failed (don't retry forever).
- Detect block/CAPTCHA pages explicitly → mark failed + alert, never loop.
- Same-day **idempotent cache**: skip listings already captured today.
- **Optional proxy support** via env (`PROXY_URL`): off by default to respect your
  budget; enable only if a store starts blocking the Actions IP. (Residential
  proxies cost money — treat as a last-resort escalation.)

**Legal/ethical:** personal/research use, public catalogue prices, no resale of raw
price data, robots respected. Keep within that scope.

---

## 8. Alerting — warn on any retrieval failure (REQUIRED)

A small **notifier** module (Telegram bot **or** Discord webhook — both free; pick
one, config via secret `ALERT_WEBHOOK`/`TELEGRAM_TOKEN`+`CHAT_ID`).

**Triggers (push a message):**
- Any store's scrape run `status` = `failed` or `partial`.
- A store-day `coverage` below threshold (default **0.85**).
- A canonical product missing for **≥3 consecutive days** (basket decay).
- Block/CAPTCHA detected on a store.
- Compute job error, or no metrics written for a day.

**Message contents:** date, store, mode, attempted/ok/failed counts, coverage, and
the top error reasons — enough to act without opening the DB.

**Backups & summary:**
- **GitHub Actions native email** on workflow failure (zero-config safety net).
- Optional **daily digest** message (OK vs failed per store) even on success, so you
  have a heartbeat and notice silent degradation.
- `scrape_runs.alerted` prevents duplicate spam for the same incident.

---

## 9. API (FastAPI)

Read-only over `inflation_metrics` (+ supporting reads).

| Method | Path | Returns |
|--------|------|---------|
| GET | `/inflation/latest` | latest overall, all periods/families/bases |
| GET | `/inflation/series?family=&dimension=&value=&period=&basis=` | time series |
| GET | `/categories` | ECOICOP tree + latest per-class inflation + weights |
| GET | `/stores` | per-store inflation + last successful scrape |
| GET | `/products` | basket contents + per-product price history |
| GET | `/health` | last scrape/compute timestamps + current coverage |

---

## 10. Scheduling & budget

- `scrape.yml` — cron `0 6 * * *` (06:00 Lisbon): basket + category crawl, all stores.
- `compute.yml` — `0 7 * * *` (or `workflow_run` after scrape): rebuild metrics; refresh
  Eurostat weights weekly/at year start.
- Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, alert creds, optional `PROXY_URL`.
- `workflow_dispatch` on both for manual runs.

**Budget:** ~120 products × 4 stores × 365 ≈ 175k snapshot rows/year + category
aggregates — comfortably inside Supabase free 500 MB. Playwright runs are minutes/day,
well inside free Actions minutes (unlimited on public repos). No paid services for v1.

---

## 11. Phased build plan

**Phase 1 — Foundation + multi-store ingest**
1. Supabase schema (§4) as a migration.
2. Eurostat weights fetcher → `categories` + `hicp_weights_cache` (PT, latest year).
3. Seed `stores` (Continente, Pingo Doce, Auchan, Lidl), ECOICOP categories,
   `products` basket + `product_listings` (URLs), EAN matching where available.
4. Per-store scraper sharing a common interface, **with the §7 anti-bot layer** and
   **§8 alerting**, writing `price_snapshots` + `scrape_runs`. Idempotent.
5. `scrape.yml` daily.
*Exit:* prices from all four stores land daily; failures alert you; re-runnable.

**Phase 2 — Metrics (both families, both bases) + dynamic crawl**
6. Category crawl → `category_observations`.
7. SQL/Python compute (§6) → `inflation_metrics` for every available period.
8. `compute.yml` nightly; weights auto-refresh.
9. Hand-reconcile a few numbers to confirm correctness.
*Exit:* daily/weekly inflation exists for fixed + dynamic families, both bases.

**Phase 3 — Simple web app**
10. FastAPI endpoints (§9).
11. Next.js page: headline number, ECOICOP breakdown, time-series charts,
    headline-vs-effective gap, store comparison, coverage indicator.
*Exit:* a shareable page showing today's Portuguese grocery inflation.

---

## 12. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Site DOM/JSON changes | `raw_payload` enables reprocessing; coverage-drop alert |
| Bot blocking | §7 layer; backoff; optional proxy escalation; alert on CAPTCHA |
| Cross-store mismatch | EAN-first matching; `match_method` audit; manual fallback |
| Products discontinued | `is_active` + ≥3-day-missing alert + weekly basket-health check |
| Partial HICP coverage | re-normalize weights within covered subset; label index honestly |
| Promo noise on daily | dual basis + 7-day MA |
| Substitution bias | inherent to HICP too; documented; revisit basket quarterly |
| Yearly metric absent year 1 | expected; emit only when lookback exists |
| Weights change annually | fetched from Eurostat, not hardcoded; refresh job |

---

*Build Phase 1 first. Do not skip `raw_payload` capture, `scrape_runs` logging, the
anti-bot layer, or the alerter — they are what make this maintainable and trustworthy.
Pull HICP weights from Eurostat `prc_hicp_inw` (PT, latest year); never hardcode them.*
