# Fuel prices (Part C — first prototype)

National daily average price for 3 vehicle fuel types (gasoline 95, diesel,
LPG auto), sourced from DGEG's public "Preço Médio Diário" statistics page
(`precoscombustiveis.dgeg.gov.pt`) — not the per-station bulk dataset, which
requires a formal data-sharing agreement with the Director-General of
Energy and Geology that hasn't been pursued. This page's footer explicitly
states the data is free for non-commercial use, matching this project's
scope. `robots.txt` doesn't exist on this subdomain (both a plain request
and a real browser navigating to it simply time out), so the usual
`RobotsChecker` is skipped here rather than risk hanging indefinitely on a
fetch that will never resolve — the page's own stated terms are the
operative permission instead.

## Scope

- **In scope this round**: national daily average for gasoline 95, diesel,
  LPG auto. `scrape_date` is DGEG's own most-recently-available date for
  that fuel type (there's a reporting lag — a day's run typically records
  yesterday's finalized figure, not today's), not the Lisbon "today"
  convention `scraper/db.py` uses for groceries.
- **Deliberately out of scope**: domestic bottled/piped gas (butano/
  propano) — no source found yet that's both authoritative and cleanly
  scrapable; per-brand/per-station comparison (Galp, BP, Repsol, etc.) —
  would need the formal DGEG data-sharing agreement or scraping individual
  brand sites directly. Both are intended future directions once pursued.
- **No compute/index logic yet** — this is data collection only, same
  starting point category crawl had before `metrics/` existed.

## Schema

`fuel_prices` (migration `0004_fuel_prices.sql`) is deliberately independent
of `stores`/`products` — a national average has no brand, package size, or
store_id, so forcing it through the grocery schema would misrepresent what
it is.

## Usage

`python -m fuel.run --source dgeg` — fetches all 3 fuel types' latest
available price and upserts into `fuel_prices` (idempotent on
`(fuel_type, scrape_date)`). Scheduled daily via `.github/workflows/fuel.yml`.
