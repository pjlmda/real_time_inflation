# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The system is built and running — this is no longer a spec-only repo. [inflation-tracker-plan.md](inflation-tracker-plan.md) is the original Portugal-only build spec and remains the authoritative source for methodology and the base data model; implement against it phase by phase (§11) rather than deviating from its architecture without reason. For what's actually true *today* — real row counts, real bugs found and fixed, where the code has diverged from the spec — read [docs/system-overview.md](docs/system-overview.md) instead, and keep it current after significant work rounds rather than letting it drift the way it did before. See "Related documents" below for the full set of living docs this project maintains.

## What this project is

A daily-updating grocery-inflation index, launched in Portugal and expanding internationally one country at a time, built by scraping online supermarket prices and computing an index methodologically aligned with INE/Eurostat HICP (ECOICOP v2 / UN COICOP 2018 classification) so results are comparable to official figures.

Key confirmed decisions (plan §0, extended since):
- Multiple stores per country: Portugal runs Continente, Pingo Doce, and Auchan actively (Lidl seeded but inactive), config-driven via `config/stores.yaml`, more addable later. France is the second country — see "Multi-country expansion" below.
- Two index families computed in parallel: a **fixed-basket** index (primary, HICP-comparable) and a **dynamic category-average** index (robustness/self-healing).
- Two price bases tracked in parallel: **headline** (regular price) and **effective** (displayed/promo price) — the gap between them is itself a signal (promo intensity).
- HICP category weights are fetched programmatically, per country, from the Eurostat dissemination API (dataset `prc_hicp_inw`, `geo=<country>`, latest year) — **never hardcoded**, refreshed yearly (`python -m weights.eurostat --geo <XX>`).
- History accrues from day 1; weekly/monthly/yearly rates are only emitted once enough lookback history exists.

## Multi-country expansion

Countries are adopted **one at a time, deliberately** — there's no fixed cap on how many this eventually covers, but each new country goes through the same live-verification-heavy process (real site research, an honest anti-bot check, real basket curation with live-confirmed EANs/prices/selectors) before being trusted. Nothing about a new country's stores, selectors, or pricing model is ever assumed to work the same way as the last country's — confirm it live, the same discipline already applied to every Portuguese store and to France.

- **Portugal** — the original, fully built market (see "Phased build plan" below — Phases 1–3 are done).
- **France** — second country, two stores live. Auchan France (`scraper/auchan_france.py`): not bot-blocked, but shows no price anywhere until a Drive pickup location is confirmed once per session — France's online grocery pricing is genuinely local, unlike Portugal's single national price. Two locations are tracked (Paris and Marseille), not one, for the same reason Portugal tracks multiple stores — confirmed live to have real, different prices on the same day. Lidl France (`scraper/lidl_france.py`): not bot-blocked either, and simpler — one national price, no location gating, same model as Portugal. Its `RobotsChecker` fetch had to move from stdlib `urllib` to `httpx` (some CDNs' certificate chains aren't completable by stdlib `ssl`, confirmed for Lidl's `myracloud` CDN), and `detect_block()` needs rendered visible text rather than raw HTML for Lidl specifically (a JS config value was false-triggering the generic "captcha" marker on every page). See [docs/france-expansion-plan.md](docs/france-expansion-plan.md) for the full research and both build writeups.
  - **E.Leclerc** (France's #1 chain by market share) is a real target for this project, but direct scraping is blocked — confirmed live behind DataDome. Adding it doesn't mean building bot-mitigation bypass tooling; see "Anti-bot scraping requirements" below for how this project handles a blocked-but-wanted target.
- **Priorities after France, in this order**: Germany, then the UK, then the US — per the bottleneck analysis in [docs/future-roadmap.md](docs/future-roadmap.md) Part 2. Germany is the cheapest next step (still an EU member, so `weights/eurostat.py` needs only a `geo=DE` change, no new code — confirmed live). The UK needs a new ONS-based weights fetcher (no longer reports into Eurostat post-Brexit). The US is the largest lift of the three — no clean COICOP-equivalent crosswalk to BLS CPI data exists, which is a real methodology gap, not just an engineering one.
- **Germany** — research done, not yet built. Same pattern as France: the biggest chains (Edeka, REWE, Kaufland, Aldi Süd, Netto) are all confirmed live behind Akamai or Cloudflare; Lidl is the one open door again, and its `robots.txt` is close enough to Lidl France's to suspect the same underlying platform. See [docs/germany-expansion-plan.md](docs/germany-expansion-plan.md). Recommended sequencing: build Lidl France first (already planned, not started), since it likely transfers to Lidl Germany with much less effort than a from-scratch build.

### What multi-country support requires structurally (migration 0007 — done for the schema fork; extend the same way for each new country)

- `stores.country` — read from `config/stores.yaml` per store (a real bug once had this hardcoded to `'PT'` for every store regardless of config — watch for that class of mistake in any code that touches per-store data).
- `category_weights(ecoicop2_code, country, hicp_weight, weight_year)` — HICP weights are country-specific even though the COICOP code/name taxonomy in `categories` itself is shared and country-agnostic. Always read/write weights through `category_weights` scoped by country; `categories.hicp_weight`/`weight_year` are deprecated (kept only until every consumer is confirmed migrated, then dropped).
- `inflation_metrics.country` — folded into the table's uniqueness constraint. Any cross-store aggregation (`overall`/`category` dimensions) **must** filter by country before aggregating — COICOP codes and `dimension_value='ALL'` collide across countries otherwise. This was a real, silent-corruption-risk bug caught and fixed in `metrics/compute.py`/`metrics/category_compute.py` before any second country's data existed; don't reintroduce an unscoped cross-store query.
- `scrape_date`/idempotency logic must use each store's own timezone (`scraper/db.py:scrape_date_for_timezone(timezone_id)`, sourced from `StoreConfig.timezone_id`), never a hardcoded Portugal constant — Portugal and most of the rest of Western Europe are a full hour apart year-round, not just during DST transitions.
- `web/api/db.py` is deliberately pinned to a single `ACTIVE_COUNTRY` for now (the live dashboard has no market switcher yet) — extend this deliberately when a second country's data is ready to surface there, not by silently removing the filter.

## Planned architecture (plan §2–3) — Phase 3 is live, not planned

```
GitHub Actions cron (twice daily, per store)
  → Scraper (Python + Playwright, stealth + anti-bot layer, §7)
    → Supabase Postgres (raw price_snapshots + dimension tables)
      → Metrics builder (SQL views + thin Python orchestrator; weights from Eurostat API, per country)
        → inflation_metrics table
          → FastAPI (read-only) → Next.js web app (Vercel), live — includes a client-side
            personalized-weights view (/personalize) on top of the same official data
  → Alerter (Telegram) on any scrape failure or low coverage (§8)
```

- Scraping: Playwright (Python) with stealth patches; prefer parsing embedded JSON/microdata over raw DOM-text scraping where a site exposes it (confirmed reliable for both Continente's JSON-LD and Auchan France's schema.org `[itemprop='price']`).
- All computation math lives in Python (`metrics/formulas.py`, pure functions; `metrics/compute.py`/`metrics/category_compute.py` orchestrate the Supabase reads/writes) — not SQL views, a deliberate deviation from the original spec once code existed.
- Scheduling is two separate GitHub Actions workflows: `scrape.yml` (twice daily, idempotent same-day retry) and `compute.yml` (`workflow_run` after scrape); both support `workflow_dispatch` for manual runs. New countries' stores aren't added to the scheduled matrix until their basket is stable — manual-run only until then (`python -m scraper.run --store <slug> --mode basket`).

## Data model (plan §4, extended by migration 0007)

Postgres/Supabase, fixed-first and multi-store from day one. Core tables and why they exist:
- `stores` — store registry (slug, base_url, robots_checked_at, **country**).
- `categories` — the shared, country-agnostic ECOICOP v2 hierarchy (code/name taxonomy only — weights live elsewhere).
- `category_weights` — **(ecoicop2_code, country) → hicp_weight/weight_year**, from Eurostat, one row set per country.
- `products` — the canonical fixed basket, one row per good, matched cross-store primarily by **EAN**.
- `product_listings` — store-specific identity for a product (URL, store_sku, `match_method`: ean/manual/fuzzy).
- `price_snapshots` — **append-only** fact table, one row per listing per day; carries both `price` (effective) and `regular_price` (headline), normalized `price_per_unit`, and a `raw_payload` jsonb blob so history is always reprocessable. This append-only design is what makes the index auditable — never update/delete rows in place.
- `category_observations` — per store × ECOICOP class × day aggregates (median/mean/p25/p75) from the dynamic category crawl; feeds the category-average index.
- `inflation_metrics` — computed output, keyed by `(as_of_date, index_family, period, dimension, dimension_value, price_basis, country)`.
- `scrape_runs` — observability table driving alerting (attempted/ok/failed counts, coverage, status).
- `hicp_weights_cache` — audit snapshot of every fetched Eurostat weight, per country.

## Methodology (plan §6) — mirror HICP elementary-aggregate approach

- Elementary relative per product: `price_i,t / price_i,0`.
- Per ECOICOP class: **Jevons geometric mean** of elementary relatives, weighted — `class_index_t = ( Π_i (price_i,t / price_i,0)^{w_i} ) × 100`.
- Overall index: weighted **arithmetic** mean of class indices using that country's `hicp_weight` (`category_weights`, not `categories`).
- Inflation rate over period P: `(index_t / index_{t-P} − 1) × 100`, only emitted once `index_{t-P}` exists. Daily headline is a **7-day moving average** (`index_value_ma7`, raw daily is noisy from rounding/promos).
- Gaps/substitutions: missing product → carry last observed price forward, exclude from `n_products`, lower `coverage`; `coverage < 0.85` on any store-day is flagged low-confidence and triggers an alert.
- Because only a supermarket-buyable subset of HICP is covered (COICOP divisions 01, 02.1, 05.6.1, 12.1.x — plan §5), weights are **re-normalized within the covered subset** to sum to 1. Always label the result as a "supermarket HICP-comparable" index, not the full HICP — this applies per country, not just Portugal.

## Anti-bot scraping requirements (plan §7 — required, not optional)

Scope is limited to respectful, resilient scraping of public catalogue prices — **not defeating auth or hard security**. That line doesn't move regardless of how much a blocked retailer is wanted:
- Persistent browser context per store, stealth patches (no `navigator.webdriver`, realistic fingerprint, locale/timezone matched to that store's own market), rotating real desktop user-agents.
- Low concurrency (1 tab per store, stores in parallel at most), randomized 2–5s jittered delays between pages.
- Respect `robots.txt` and `Crawl-delay`; exponential backoff honoring `Retry-After` on 403/429/5xx with capped retries; explicit block/CAPTCHA detection that marks the run failed rather than looping.
- Idempotent same-day cache (skip listings already captured today, per that store's own timezone).
- Optional proxy via `PROXY_URL` env var, off by default — only enable as a last resort if a store starts blocking the Actions IP.

**Where a wanted retailer is protected by enterprise-grade bot mitigation** (DataDome, Cloudflare Enterprise, Akamai, PerimeterX — confirmed live for Leclerc, Carrefour, Intermarché, and Système U in France) such that direct scraping isn't viable within the scope above, don't automatically write that retailer off. Evaluate legitimate third-party data sources instead — an official partner/affiliate API, or a licensed data-as-a-service provider — with the same live-verification scrutiny already applied to everything else in this project (real cost, real terms of service, real data quality/freshness, not just a search result that looks promising). This is a sourcing decision, not a license to build CAPTCHA-solving or fingerprint-evasion tooling ourselves — that stays out of scope no matter which retailer is on the other end.

**Commercial anti-detection proxy/scraping-API providers (ScraperAPI, Scrape.do, ScrapingAnt, Bright Data, Oxylabs, and similar) are explicitly out of scope**, and are not "licensed data-as-a-service providers" under the rule above — their core product for a protected target is proxy rotation, fingerprint spoofing, and CAPTCHA solving specifically to defeat the bot mitigation that target deployed on purpose. Routing a request through one of these services doesn't create authorization from the target site that wouldn't otherwise exist, whether the request is built here or by a vendor paid to do it on our behalf — don't integrate with them for any blocked retailer, in France or any future country. A "licensed data-as-a-service provider" means an actual authorized relationship to the target's data (an official partner/affiliate API, or a commercial panel-data provider like Kantar/NielsenIQ/Circana) — the underlying access has to be authorized by the retailer itself, not just technically capable of getting past their defenses.

## Alerting requirements (plan §8 — required)

A notifier (Telegram, `alerting/telegram.py`) must fire on: any `scrape_runs.status` of `failed`/`partial`, coverage below 0.85, a canonical product missing ≥3 consecutive days, CAPTCHA/block detection, or a compute job error / missing daily metrics. `scrape_runs.alerted` prevents duplicate alerts for the same incident. GitHub Actions' native failure email is the zero-config backup.

## Phased build plan (plan §11) — Phases 1–3 done for Portugal; multi-country is the current phase

1. **Phase 1 — Foundation + multi-store ingest**: done. Supabase schema, Eurostat weights fetcher, seed stores/categories/products/listings, per-store scraper (shared `BaseScraper` interface, anti-bot + alerting), `scrape.yml`.
2. **Phase 2 — Metrics + dynamic crawl**: done. Category crawl → `category_observations`, Python compute → `inflation_metrics` for all available periods, `compute.yml`.
3. **Phase 3 — Web app**: done. FastAPI read-only endpoints + Next.js dashboard, live on Vercel, including the personalized-weights view.
4. **Current phase — multi-country expansion**: not part of the original spec; see "Multi-country expansion" above and [docs/france-expansion-plan.md](docs/france-expansion-plan.md) for where France stands.

Non-negotiables, unchanged since the original spec and unchanged by expansion into new countries: don't skip `raw_payload` capture, `scrape_runs` logging, the anti-bot layer, or the alerter — they're what make the tracker maintainable and trustworthy. Always pull HICP weights from Eurostat `prc_hicp_inw` programmatically per country; never hardcode them.

## Related documents

- [inflation-tracker-plan.md](inflation-tracker-plan.md) — the original build spec (Portugal-only as written; methodology and base data model are still authoritative).
- [docs/system-overview.md](docs/system-overview.md) — living "as-built" status doc: real row counts, real bugs found/fixed, where code has diverged from the spec. Check it before trusting a claim from the spec doc about current state.
- [docs/future-roadmap.md](docs/future-roadmap.md) — planning doc for personalized category weights (shipped a v1 since this was written — see system-overview.md) and the multi-country bottleneck analysis (anti-bot difficulty, maintainer time, weights-API reuse, currency/locale plumbing, infra cost) behind the Germany/UK/US sequencing above.
- [docs/france-expansion-plan.md](docs/france-expansion-plan.md) — France-specific research and status: market-share data, live anti-bot findings for all six major chains, the Auchan Drive-location mechanic, current basket.
- [docs/germany-expansion-plan.md](docs/germany-expansion-plan.md) — Germany-specific research: market-share data, live anti-bot findings, the Lidl France/Germany platform-similarity lead. Planning only — nothing built yet.
- [seed/README.md](seed/README.md) — basket curation methodology and history: real curation decisions, simplifications, and bugs found while building out each store's product list.
- [db/migrations/README.md](db/migrations/README.md) — migration process (numbered, forward-only, applied manually via the Supabase SQL editor — no automated migration runner exists).
