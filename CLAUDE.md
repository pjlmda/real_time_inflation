# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains only the build spec — [inflation-tracker-plan.md](inflation-tracker-plan.md) — no code has been written yet. That document is the source of truth: implement it phase by phase (§11) rather than deviating from its architecture or data model. When you start writing code, follow the structure it lays out below; when decisions in the plan turn out to be wrong once code exists, update the plan doc alongside the code change so it stays authoritative.

## What this project is

A daily-updating grocery-inflation index for Portugal, built by scraping online supermarket prices and computing an index methodologically aligned with INE/Eurostat HICP (ECOICOP v2 / UN COICOP 2018 classification) so results are comparable to official figures.

Key confirmed decisions (plan §0):
- Multiple stores from day one: Continente, Pingo Doce, Auchan, Lidl — config-driven, more addable later.
- Two index families computed in parallel: a **fixed-basket** index (primary, HICP-comparable) and a **dynamic category-average** index (robustness/self-healing).
- Two price bases tracked in parallel: **headline** (regular price) and **effective** (displayed/promo price) — the gap between them is itself a signal (promo intensity).
- HICP category weights for Portugal are fetched programmatically from the Eurostat dissemination API (dataset `prc_hicp_inw`, geo=PT, latest year) — **never hardcoded**, refreshed yearly.
- History accrues from day 1; weekly/monthly/yearly rates are only emitted once enough lookback history exists.

## Planned architecture (plan §2–3)

```
GitHub Actions cron (06:00 Lisbon)
  → Scraper (Python + Playwright, stealth + anti-bot layer, §7)
    → Supabase Postgres (raw price_snapshots + dimension tables)
      → Metrics builder (SQL views + thin Python orchestrator; weights from Eurostat API)
        → inflation_metrics table
          → FastAPI (read-only) → Next.js web app (Vercel) [Phase 3]
  → Alerter (Telegram/Discord) on any scrape failure or low coverage (§8)
```

- Scraping: Playwright (Python) with stealth patches; prefer parsing embedded JSON over DOM scraping.
- All computation math lives in SQL for auditability, orchestrated by thin Python.
- Scheduling is two separate GitHub Actions workflows: `scrape.yml` (06:00 Lisbon) and `compute.yml` (07:00 or `workflow_run` after scrape); both support `workflow_dispatch` for manual runs.

## Data model (plan §4)

Postgres/Supabase, fixed-first and multi-store from day one. Core tables and why they exist:
- `stores` — store registry (slug, base_url, robots_checked_at).
- `categories` — ECOICOP v2 hierarchy with `hicp_weight` (from Eurostat) per leaf class.
- `products` — the canonical fixed basket, one row per good, matched cross-store primarily by **EAN**.
- `product_listings` — store-specific identity for a product (URL, store_sku, `match_method`: ean/manual/fuzzy).
- `price_snapshots` — **append-only** fact table, one row per listing per day; carries both `price` (effective) and `regular_price` (headline), normalized `price_per_unit`, and a `raw_payload` jsonb blob so history is always reprocessable. This append-only design is what makes the index auditable — never update/delete rows in place.
- `category_observations` — per store × ECOICOP class × day aggregates (median/mean/p25/p75) from the dynamic category crawl; feeds the category-average index.
- `inflation_metrics` — computed output, keyed by `(as_of_date, index_family, period, dimension, dimension_value, price_basis)`.
- `scrape_runs` — observability table driving alerting (attempted/ok/failed counts, coverage, status).
- `hicp_weights_cache` — audit snapshot of fetched Eurostat weights.

## Methodology (plan §6) — mirror HICP elementary-aggregate approach

- Elementary relative per product: `price_i,t / price_i,0`.
- Per ECOICOP class: **Jevons geometric mean** of elementary relatives, weighted — `class_index_t = ( Π_i (price_i,t / price_i,0)^{w_i} ) × 100`.
- Overall index: weighted **arithmetic** mean of class indices using `hicp_weight`.
- Inflation rate over period P: `(index_t / index_{t-P} − 1) × 100`, only emitted once `index_{t-P}` exists. Daily headline is a **7-day moving average** (raw daily is noisy from rounding/promos).
- Gaps/substitutions: missing product → carry last observed price forward, exclude from `n_products`, lower `coverage`; `coverage < 0.85` on any store-day is flagged low-confidence and triggers an alert.
- Because only a supermarket-buyable subset of HICP is covered (COICOP divisions 01, 02.1, 05.6.1, 12.1.x — plan §5), weights are **re-normalized within the covered subset** to sum to 1. Always label the result as a "supermarket HICP-comparable" index, not the full HICP.

## Anti-bot scraping requirements (plan §7 — required, not optional)

Scope is limited to respectful, resilient scraping of public catalogue prices — not defeating auth or hard security:
- Persistent browser context per store, stealth patches (no `navigator.webdriver`, realistic fingerprint, pt-PT locale, Europe/Lisbon timezone), rotating real desktop user-agents.
- Low concurrency (1 tab per store, stores in parallel at most), randomized 2–5s jittered delays between pages.
- Respect `robots.txt` and `Crawl-delay`; exponential backoff honoring `Retry-After` on 403/429/5xx with capped retries; explicit block/CAPTCHA detection that marks the run failed rather than looping.
- Idempotent same-day cache (skip listings already captured today).
- Optional proxy via `PROXY_URL` env var, off by default — only enable as a last resort if a store starts blocking the Actions IP.

## Alerting requirements (plan §8 — required)

A notifier (Telegram bot or Discord webhook, pick one) must fire on: any `scrape_runs.status` of `failed`/`partial`, coverage below 0.85, a canonical product missing ≥3 consecutive days, CAPTCHA/block detection, or a compute job error / missing daily metrics. `scrape_runs.alerted` prevents duplicate alerts for the same incident. GitHub Actions' native failure email is the zero-config backup.

## Phased build plan (plan §11)

Build in this order — do not skip ahead to Phase 3 before Phases 1–2 are solid:
1. **Phase 1 — Foundation + multi-store ingest**: Supabase schema migration, Eurostat weights fetcher, seed stores/categories/products/listings, per-store scraper (shared interface, anti-bot + alerting), `scrape.yml`.
2. **Phase 2 — Metrics + dynamic crawl**: category crawl → `category_observations`, SQL/Python compute → `inflation_metrics` for all available periods, `compute.yml`, hand-reconcile numbers.
3. **Phase 3 — Simple web app**: FastAPI read-only endpoints (§9), Next.js page (headline number, ECOICOP breakdown, time series, headline-vs-effective gap, store comparison, coverage indicator).

Non-negotiables per the plan's closing note: don't skip `raw_payload` capture, `scrape_runs` logging, the anti-bot layer, or the alerter — they're what make the tracker maintainable and trustworthy. Always pull HICP weights from Eurostat `prc_hicp_inw` programmatically; never hardcode them.
