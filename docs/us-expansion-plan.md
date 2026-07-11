# United States Expansion Plan

Written 2026-07-11 in response to a direct request to study the US next
(UK explicitly deferred). Started as a research-only document mirroring
every other country's live-verification-heavy research phase, including
the ones that ended up shelved (`docs/germany-expansion-plan.md`) — but
the same day, per explicit instruction to keep building, `scraper/
wegmans.py` was written and verified with a real 58-product basket across
four locations (see §6, §8, §9), and `weights/bls.py` was built (§7).
**Merged to `main` 2026-07-11** (fast-forward from the `research/us-
expansion` branch, which incubated all of this work) **and added to
`scrape.yml`'s scheduled matrix the same day** — all four locations now
scrape twice daily alongside every other store. `category_weights` still
has no US rows (the BLS API's daily quota was exhausted by this session's
research before a full sync could run — needs a re-run once it resets),
so no `inflation_metrics` exist for the US yet; this covers `price_snapshots`
only so far.

**Bottom line up front (updated after a second research pass, same day)**:
**Wegmans is a real, live-confirmed, unblocked lead** — not bot-blocked
(zero enterprise bot-mitigation cookies across a full session), the
cleanest `robots.txt` of any of the 17 chains checked (`Allow: /`,
unconditional), real structured per-product prices *and* price-per-unit,
stable PDP URLs, and a real UPC/barcode embedded in page data — better
EAN-equivalent access than either Lidl France or Lidl Germany got. It's a
regional chain (Northeast US only), so a US launch on Wegmans alone would
be a narrower slice than Portugal's, the same honest framing already
applied to Auchan-only France. H-E-B is now confirmed **blocked** (an
explicit anti-bot error page, not the inconclusive blank shell first
recorded). The other 15 chains checked are unchanged: top 4 by market share
(Walmart, Kroger, Costco, Target) all confirmed behind enterprise bot
mitigation; Aldi US has a real catalog but its own `robots.txt` disallows
all crawling, ruling it out by policy regardless of technical scrapability.
On weights: BLS does publish a real COICOP/HICP crosswalk (correcting
`CLAUDE.md`'s prior "no clean crosswalk" claim), and a third pass
**fully resolved** the access question in the best possible direction:
`www.bls.gov` (the R-COICOP/R-HICP `.xlsx` files) and `download.bls.gov`
(BLS's bulk flat-file service) are both Akamai-blocked, the latter with an
explicit stated anti-automation policy — but the exact same unauthenticated
`api.bls.gov` JSON endpoint already confirmed live serves current,
correctly-structured expenditure-weight ("relative importance") data
directly, **no API key or registration needed at all**, confirmed at both
a broad-aggregate and fine-grained item level. Net: Wegmans is a genuine,
promising candidate worth a real DOM/pricing spike next; the weights side
is now a bounded, well-understood, freely-accessible data source, not an
open access question.

---

## 1. Market landscape

### Market share (2025-2026, Statista / Progressive Grocer / GourmetPro)

| Chain | Approx. US grocery market share | Notes |
|---|---|---|
| Walmart | 23.6% (~$276bn) | Supercenters, Neighborhood Markets, fast-growing e-commerce |
| Kroger | 10.1% (~$147bn) | Largest traditional supermarket chain, 2,750+ stores, many banners |
| Costco | 9.2% (~$97bn) | Membership warehouse, only ~600 locations — highest revenue/store |
| Albertsons | 6.4% (~$80.4bn) | Owns Safeway, Jewel-Osco, Vons, Shaw's, Acme |
| Publix | 4.1% | Employee-owned, Southeast-concentrated |

Top 5 chains: 53.4% combined. Top 10: ~70% combined — a more concentrated
market at the very top than either Portugal or France, but with a long tail
of large regional players (H-E-B, Wegmans, Meijer, WinCo, Trader Joe's,
Whole Foods/Amazon) that don't show up in a top-5 cut.

Sources: [Statista — Grocery retailers market share U.S. 2025](https://www.statista.com/statistics/1450393/leading-grocery-store-by-market-share-us/), [Progressive Grocer — Walmart Holds Tight to 1st Place](https://progressivegrocer.com/walmart-holds-tight-1st-place-grocery-market-share), [GourmetPro — 10 Largest Grocery Chains in the USA](https://www.gourmetpro.co/blog/largest-grocery-chains-usa/)

### Anti-bot posture — checked live 2026-07-11 (16 chains)

| Chain | Result |
|---|---|
| **Walmart** | Not blocked at the HTTP layer, but a real Playwright session hitting `/search?q=milk` renders a page titled **"Robot or human?"** — an explicit bot challenge. |
| **Kroger** | `net::ERR_HTTP2_PROTOCOL_ERROR` on a real Playwright session — connection-level rejection before a normal response is even returned. |
| **Costco** | 200 OK, but the response sets `_abck` and `bm_sz` cookies — confirmed **Akamai Bot Manager** signature. |
| **Target** | 200 OK on a single probe (real prices rendered), but sets `_pxhd` — confirmed **PerimeterX/HUMAN Security** signature. Per `CLAUDE.md`'s own policy, a known enterprise bot-mitigation vendor being present is disqualifying regardless of whether one test request slipped through; a sustained scraper making regular real requests is a different exposure than a single research probe. |
| **Albertsons** | 403 direct. |
| **Safeway** (Albertsons banner) | 403 direct. |
| **Trader Joe's** | 403 direct; empty `robots.txt`. |
| **Meijer** | Real Playwright session → page titled "Access Denied". |
| **WinCo Foods** | 403, page titled "Attention Required! \| Cloudflare" — Cloudflare challenge. |
| **Aldi US** | **Not bot-blocked** — real category pages (`/store/aldi/pages/dairy-and-eggs` etc.) load with genuine prices, location-aware ("Shopping at ALDI - BAT 18 - Geneva, IL", auto-detected delivery window). Structurally the strongest lead of the sixteen. **But its `robots.txt` ends with a catch-all `User-Agent: * / Disallow: /`** — only specific named crawlers (Googlebot, Bingbot, etc.) get an explicit `Allow:`. A generic scraper isn't permitted by the site's own policy; impersonating an allow-listed crawler's user-agent to get around that would be exactly the kind of evasion `CLAUDE.md`'s anti-bot section rules out. This is a clean, explicit "no" from the retailer itself, not a technical obstacle. |
| **Sprouts Farmers Market** | 200 OK, no block markers on a single probe — not deeply investigated beyond that. |
| **Publix** | Homepage/search probes kept redirecting to a generic "International" landing page rather than real search results — inconclusive, the correct US storefront entry point wasn't found in this pass. `robots.txt` returned empty. |
| **H-E-B** | **Confirmed blocked**, on a second, deeper pass. The earlier "489-byte blank shell" turned out to be an explicit anti-automation error page once the raw HTML was inspected directly: `{"errorCode": "15", "description": "This page could not load. It looks like an ad blocker, antivirus software, VPN, or firewall may be causing an issue...", ...}`, served with an `x-iinfo` edge-proxy header — textbook bot-mitigation messaging (blaming client-side tools rather than stating a block), just formatted as JSON instead of a CAPTCHA page. `robots.txt` being permissive doesn't matter once the edge itself is rejecting the request. |
| **Wegmans** | **Confirmed live, not bot-blocked, real working catalog.** `robots.txt`: `Allow: /` unconditional (cleanest of all 17 chains), plus a sitemap and an explicit `Content-Signal: search=yes` header. A full session (homepage → category → leaf subcategory → product-detail page) rendered real content throughout: the homepage itself surfaced a real priced product ("Wegmans Greek-Style Turkey Patties, 12 ounce, $8.99/ea, $0.75/ounce"); the `Dairy` → `Milk` leaf category showed a real product grid with price *and* price-per-unit for every item (e.g. "Wegmans Vitamin D Whole Milk, 1 gallon, $2.99/ea, $2.99/gallon"); a direct product-detail page (`/shop/product/94427-Vitamin-D-Whole-Milk`) loaded cleanly with a **real UPC embedded in page JSON** (`"upc":["00077890944271"]`) — better barcode access than either Lidl France or Lidl Germany got. Zero enterprise bot-mitigation cookies (`_abck`, `bm_sz`, `_pxhd`, `_px3`, `incap_ses`, `reese84`, `__cf_bm`, `datadome`) appeared anywhere across the session. A store-location selector exists (defaulted to "Medford" — a real US-scoped location, not obviously IP-geolocation-only, since a real clickable modal with `aria-haspopup="dialog"` sits behind it) — the interaction wasn't fully driven through in this pass, but the mechanism is confirmed present, the same shape as Auchan France's Drive-location flow. |

Pattern: the same shape as France and Germany for the market leaders —
Akamai at Costco, PerimeterX at Target, Cloudflare at WinCo, an explicit
bot-mitigation error page at H-E-B, unnamed challenge systems at
Walmart/Meijer — but **Wegmans breaks the pattern**: a real, regional
(Northeast US) chain that is genuinely open, the same way Lidl turned out
to be in both France and Germany, just a smaller chain than either Lidl
market position.

---

## 2. What's the same as every other country

- **Schema/methodology**: `stores.country='US'`, `category_weights` scoped
  by country, Jevons/weighted-arithmetic formulas — no changes needed, this
  is exactly what migration 0007 was built to support.
- **Anti-bot layer**: `scraper/antibot.py`'s stealth patches, backoff,
  robots.txt respect, and block detection all apply unchanged.

## 3. What's different — real, not yet resolved

### 3.1 The BLS weights crosswalk is real but has real caveats (corrects `CLAUDE.md`)

`CLAUDE.md` currently states "no clean COICOP-equivalent crosswalk to BLS
CPI data exists, which is a real methodology gap, not just an engineering
one." That's not quite right — **BLS does publish exactly this crosswalk**,
in two forms:

- **R-COICOP** — a research series bridging US CPI item strata to COICOP
  classes, produced for the OECD since 2014, monthly.
- **R-HICP** — a research series explicitly aimed at HICP comparability
  (closer to what this project actually wants than R-COICOP). Expenditure
  weights are updated every January, with the research index released by
  end of February — the same annual refresh cadence Eurostat's
  `prc_hicp_inw` already runs on, which is a genuinely good sign for
  slotting into `weights/eurostat.py`'s existing yearly-refresh pattern.

Real caveats found, live, that keep this from being a simple "point
`weights/` at a new URL":

- **`bls.gov` itself (the HTML site hosting the R-COICOP/R-HICP `.xlsx`
  download attachments) is behind Akamai** — confirmed live, a direct
  `curl` to `bls.gov/cpi/research-series/r-hicp-home.htm` and to the
  `r-hicp-data.xlsx` attachment both return `403`, `server: AkamaiGHost`.
  The weight *files* aren't fetchable the simple way Eurostat's dissemination
  API is.
- **`api.bls.gov`, BLS's actual public JSON API, is a completely separate,
  unauthenticated, working, official channel** — confirmed live: a plain
  `POST` to `api.bls.gov/publicAPI/v2/timeseries/data/` with a series ID
  (e.g. `CUUR0000SA0` for all-items, `CUUR0000SAF11` for "food at home")
  returns real JSON time-series data with no API key needed for v1 (v2 adds
  a free registration key for higher limits). This is architecturally the
  same shape as Eurostat's API and is genuinely promising.
- **Second pass, same day — the wall is precisely `bls.gov`'s and
  `download.bls.gov`'s edges, not BLS's data policy.** BLS added "aspect
  metadata" (seasonal factors, relative importance/weights, standard
  error, etc.) tied to regular CPI series IDs in November 2024, explicitly
  described as available two ways: bulk flat files, or the public API. The
  bulk flat-file route was checked live and is a dead end —
  `download.bls.gov/pub/time.series/cu/` (a *separate* subdomain from the
  main website, dedicated to bulk downloads) returns `403`,
  `server: AkamaiGHost`, with a block page that **explicitly states BLS's
  own anti-automation policy in writing**: *"Automated retrieval programs
  (commonly called 'robots' or 'bots') can cause delays and interfere with
  other customers' timely access to information. Therefore, bot activity
  that doesn't conform to BLS usage policy is prohibited."* That's a
  clean, stated policy line, not just a technical obstacle — respecting it
  isn't optional under this project's own rules even if a technical
  bypass existed.
- **Resolved, third pass, same day — weight data is confirmed live and
  free, no registration needed.** Adding `"aspects": true` to the exact
  same unauthenticated `POST` request already confirmed working returns
  real relative-importance figures directly in the response, no v2 key
  required: `curl -X POST api.bls.gov/publicAPI/v2/timeseries/data/ -d
  '{"seriesid":["CUUR0000SEFA02"],"startyear":"2026","endyear":"2026","aspects":true}'`
  returns, for each month, an `"aspects"` array including `"Relative
  Importance": "0.133"` (this specific series was current as of May 2026).
  Confirmed at multiple levels of granularity — a broad aggregate
  (`CUUR0000SAF11`, "food at home," ~8.2% relative importance) and
  fine-grained item strata (`CUUR0000SEFA01`/`SEFA02`, ~0.04-0.13% each) —
  both return live, current, correctly-structured weight figures.
- **One real nuance, not fully resolved**: what's confirmed above is BLS's
  *native* CPI item-strata relative importance (BLS's own classification,
  e.g. "Bread"/`SEFA01`-style series), not necessarily the specific
  already-COICOP-relabeled output of the R-COICOP/R-HICP bridging process
  — that finished, bridged product may still only exist in the paused/
  blocked `.xlsx` files. This isn't a dead end either way: if the
  finished bridged file stays unreachable, this project could build its
  own BLS-item-to-COICOP crosswalk (the same kind of one-time mapping
  work Eurostat's own COICOP taxonomy already does under the hood) using
  the now-confirmed-free item-level weight data directly — a bounded,
  concrete task, not a missing data source.
- **Publication of the R-COICOP `.xlsx` was paused in December 2024**,
  per BLS's own site, "to be resumed when resources are available" — a
  live currency risk for the *finished bridged* product specifically. It
  doesn't affect the aspect-metadata/relative-importance data confirmed
  above — that's a separate, apparently still-active data product
  (added to the API in November 2024, after the R-COICOP pause, and
  showing current May-2026 data just now) — worth keeping the two
  straight rather than treating one pause as evidence about the other.

**Net on weights**: substantially better than `CLAUDE.md` previously
stated. There is a real, official crosswalk methodology (R-COICOP/R-HICP),
and — confirmed live, no registration, no key — BLS's public API freely
serves current, granular, correctly-structured expenditure-weight data for
any CPI item series. The weights side is no longer a "real methodology
gap" in the way `CLAUDE.md` described it; at worst it's a bounded mapping
task (BLS item strata → COICOP codes) using data that's already confirmed
freely accessible, not a missing or blocked data source.

### 3.2 Multi-timezone is a genuinely new complexity class

Every country built so far (Portugal, France, Germany-research) spans at
most one or two adjacent timezones. The US spans six
(`America/New_York`, `/Chicago`, `/Denver`, `/Los_Angeles`,
`/Anchorage`, `Pacific/Honolulu`). The existing per-store
`timezone_id` mechanism (`scraper/db.py:scrape_date_for_timezone`) is
already architecturally per-store, not hardcoded, so this isn't a schema
problem — but it raises a real, unanswered question this project hasn't
faced yet: does a national US chain (Walmart, Target) show one national
online price, or does pricing vary by store/region the way Auchan France's
Drive locations turned out to (discovered live, not assumed, and it
mattered enough to track two locations instead of one)? US retail is
well known for real state-level and even store-level price variation
(state/local sales tax, regional distribution costs) — this would need the
same kind of live, product-by-product comparison across two distant US
metro areas that caught Auchan France's real Paris-vs-Marseille gap,
before assuming single-location pricing is representative.

### 3.3 Currency

USD — no new plumbing needed, same as any other country (this project
already stores/display currency-per-country, not hardcoded EUR).

### 3.4 Category coverage subset may not transfer cleanly

The plan's "supermarket-buyable" subset (COICOP 01, 02.1, 05.6.1, 12.1.x)
was built against Portugal's assortment and re-verified for France without
major changes. The US has real category-boundary quirks worth checking
before assuming the same subset applies without adjustment — e.g. US
grocery/pharmacy/general-merchandise lines blur more than in EU
supermarkets (Walmart and Target sell across nearly every COICOP division
in one store), and any future US weights source (§3.1) needs its own
`geo`-equivalent scoping the same way Eurostat's `geo=<XX>` parameter
already works.

---

## 4. What would need to happen before any code

1. **Done — the `api.bls.gov` weights question is resolved.** Confirmed
   live, no registration needed: a `POST` to
   `api.bls.gov/publicAPI/v2/timeseries/data/` with `"aspects": true`
   returns current relative-importance (weight) figures for any CPI item
   series. `weights/bls.py` is buildable the way `weights/eurostat.py` is,
   modulo the BLS-item-to-COICOP mapping nuance in §3.1 — building that
   mapping (a one-time, bounded task, likely similar in spirit to how
   `seed/categories.py` already encodes the ECOICOP taxonomy by hand) is
   the real remaining weights work, not data access.
2. **Done — `scraper/wegmans.py` built, tested, and verified with a real
   58-product scrape (58/58, 100% coverage).** Full writeup in §6. Two
   sub-items from the original spike remain genuinely open, not blockers:
   the store-location selector flow (does explicit ZIP/store entry work
   reliably, or does it silently fall back to IP geolocation that might
   behave oddly from a GitHub Actions runner's IP — a quick attempt to
   click through it hit the wrong element, a hamburger-menu button with a
   similar `aria-haspopup` attribute) and live promo/regular-price
   detection (no promoted product was found across 14 category pages or
   the sign-in-gated `/shop/coupons` page, so `is_promotion` currently
   defaults to "no promotion" — the same honest starting state Auchan
   France's first build shipped with).
3. **A live single-day, multi-city price comparison** on Wegmans — it's
   regional (114 stores across NY [51], PA [19], VA [15], NJ, MD, MA, NC,
   CT, DE, and DC — verified live 2026-07-11, storelocators.com/ScrapeHero/
   World Population Review), so
   the open question isn't "national vs. regional" the way it was for
   Walmart/Target, but whether price varies *within* that footprint
   (e.g. NYC vs. a smaller upstate NY market) the way Auchan France's
   Paris vs. Marseille turned out to — checked live, not assumed.
4. **Re-verify the "supermarket-buyable" COICOP subset** against Wegmans'
   real assortment, the same live-verification discipline as every
   category-growth round in `seed/README.md`.
5. **Not further pursued for now**: H-E-B (confirmed blocked), Walmart/
   Kroger/Costco/Target/Albertsons/Safeway/Trader Joe's/Meijer/WinCo (all
   confirmed blocked), Aldi US (ruled out by its own `robots.txt`). Publix
   and Sprouts got only a shallow check and could be revisited later if
   Wegmans alone proves too narrow.

## 5. Honest framing

Wegmans is a real, live-confirmed, unblocked lead — the same shape of
finding that Lidl was for both France and Germany, just for a smaller,
Northeast-US-only regional chain rather than a national one. A US launch
on Wegmans alone starts narrower than Portugal's three-store setup, the
same "narrower slice" framing already applied to Auchan-only France —
worth stating plainly, not implying broader US coverage than exists. With
the sourcing question (Wegmans, now built — §6), the weights-access
question (BLS's free public API), and a real end-to-end scrape all
resolved positively the same day, this landed closer to a "France" outcome
(a real, reachable chain found and built) than a "Germany" one (exhausted,
shelved) — merged to `main`, no longer research-only.

## 6. Build status — `scraper/wegmans.py`, 2026-07-11

Built the same day as the research above, per explicit instruction to keep
building rather than stop at research. Full curation writeup (all 58
products, category breakdown, brand mix) is in `seed/README.md`'s
"United States: Wegmans" section — not duplicated here. Summary:

- **58 products across 14 categories** (rice, bread, pasta, beef, pork,
  poultry, milk, yoghurt, cheese, eggs, olive oil, fresh fruit, vegetables,
  personal care), ~4.1 products/category — deliberately deeper than every
  prior new store's initial basket (Auchan France started at 11/11, Lidl
  France at 12/12), per explicit instruction that a market this much
  larger in population needs more products per category for the
  within-class average to be representative and stable.
- **Real UPCs for all 58** (pulled from each PDP's embedded JSON), better
  barcode coverage than either Lidl France or Lidl Germany managed.
- **Three real bugs found and fixed**, all with the potential to silently
  corrupt data beyond just this one store — full detail in `seed/
  README.md`:
  1. `scraper/db.py` hardcoded `"currency": "EUR"` for every store,
     unconditionally — never caught before because every store built so
     far has been EUR-denominated. Fixed by adding `currency` to
     `StoreConfig`/`config/stores.yaml`, same pattern as `timezone_id`.
  2. `scraper/wegmans.py`'s price-element check used `.count()` right
     after `domcontentloaded`, which doesn't wait for anything — Wegmans
     hydrates its price block client-side, unlike every other site
     scraped so far, so the real scraper failed 57/57 on the first run
     even though the identical selector worked reliably during research
     (which always paused before checking). Fixed with an explicit
     `wait_for(state="attached")`.
  3. Two products with the same `canonical_name`+`brand` (a 5.3oz and a
     32oz Greek yogurt, both literally "0% Greek Plain Nonfat Yogurt")
     collided under `seed/load_seed.py`'s upsert key, which is
     `(canonical_name, brand)`, not `product_key` — silently merged into
     one DB row, then left a stale orphaned row behind once fixed.
     Self-diagnosed and cleaned up the same session.
- **Verified live end to end**: `python -m scraper.run --store wegmans-us
  --mode basket` → **58/58 listings, 100% coverage**, real USD prices
  confirmed in `price_snapshots` with the correct `currency`/`country`
  scoping.
- **Not done at the time**: not yet merged to `main`, not added to
  `.github/workflows/scrape.yml`'s matrix. (Update: merged to `main` after
  §8's multi-location rebuild — see the top of this document. Still not in
  `scrape.yml`'s scheduled matrix.)

## 7. Build status — `weights/bls.py`, 2026-07-11

Built the same day, immediately after the scraper (§6), closing the
§3.1/§4.1 weights-mapping gap. Full module docstring in `weights/bls.py`
has the complete provenance/verification notes per BLS item code; summary:

- **13 of 15 mapped BLS item codes were individually live-verified**
  against `api.bls.gov` during development — real current data, plausible
  relative-importance magnitude, correct parent/child nesting (e.g. Dairy's
  RI ≥ Milk's + Cheese's, Fresh fruits' RI ≥ Apples' + Bananas'). The
  remaining two (`SEFW` for wine, `SEGB` for personal care) are sourced
  from search-engine summaries cross-referenced against FRED series
  titles, not independently live-verified — the API's daily
  unauthenticated-request quota was hit mid-session from the volume of
  research this same day. Flagged in the module itself, not silently
  assumed correct.
- **Two disclosed granularity/coverage gaps**, the same "real gap, not
  worked around" pattern already used elsewhere in this project: BLS
  doesn't split rice from pasta (both map to its single `SEFA03` item,
  "Rice, pasta, cornmeal") or break out olive oil/wine from the broader
  "Fats and oils"/"Alcoholic beverages at home" items — used as the
  closest available substitute rather than fabricating a finer series that
  doesn't exist at this publication level. No BLS item was found for
  yoghurt specifically (folded into the broader Dairy aggregate at the
  level BLS publishes) — left genuinely unmapped; `01.1.4.4` won't get a
  US weight until this is resolved.
- **A real, general robustness bug found and fixed while testing this
  against the live (rate-limited) API**: `parse_response()` alone silently
  treated a declined/rate-limited API response the same as "no data for
  any of these series" — `python -m weights.bls` reported "Synced 0 weight
  records" with no indication anything had actually failed. Fixed by
  checking the response's own `status` field in `fetch_weights()` and
  raising `BlsRequestFailed` explicitly when the request wasn't processed,
  rather than letting a quiet zero-record "success" mask a real failure.
- **A second real bug found and fixed, shared code**: `weights/eurostat.py
  :upsert_weights()` hardcoded its own module's `SOURCE_DATASET` constant
  (`'prc_hicp_inw'`) directly rather than accepting it as a parameter —
  reusing that function as-is from `weights/bls.py` (a deliberate reuse,
  not a duplication, since the function was already fully country-agnostic
  otherwise) would have mislabeled every BLS-sourced `hicp_weights_cache`
  audit row as Eurostat-sourced. Fixed by adding a `source_dataset`
  parameter, defaulting to the existing Eurostat value so every existing
  caller's behavior is unchanged.
- **Tested via fixtures** (`tests/test_bls.py`, 5 tests; mirrors
  `tests/test_eurostat.py`'s established pattern), not yet via a full
  successful live `python -m weights.bls` run — the API's daily quota was
  already exhausted by the time this module was ready to run for real, so
  `category_weights` has **no US rows yet**. Needs a re-run once the quota
  resets (BLS's daily limits reset on a rolling/calendar-day basis) before
  US `inflation_metrics` can be computed at all — this is the concrete,
  well-scoped next step, not an open unknown.

## 8. Build status — multi-location rebuild, 2026-07-11

Per explicit instruction to "dive deeper on different store locations
pricing so we can find a solution" (the same open question flagged in §4.3
and §6). Confirmed live, decisively: Wegmans prices *do* vary by location,
the same class of finding as Auchan France's Paris-vs-Marseille discovery —
`Vitamin D Whole Milk` (product 94427) priced **$2.99/gallon at Medford,
NY (store 134) vs. $3.99/gallon at Manhattan, NY (store 156)**, a 33%
spread, querying the same product at different `storeNumber`s. A third
store (Fairfax, VA — store 16, $3.69/gallon) confirmed this isn't NY-only
variation.

**This finding led to a full scraper rebuild, not just a location-count
increase.** While tracing how to force a specific store (the original DOM
version had no reliable mechanism — the site resolves a default via
client-side Google Geolocation API calls, not a URL/cookie parameter), a
network trace of the "Medford" selector button revealed
`api.digitaldevelopment.wegmans.cloud/commerce/browse/products/`, a public
JSON commerce API the site's own frontend calls unauthenticated, taking
`storeNumber` as a plain query parameter. Checked before using it:
`robots.txt` on that subdomain 404s (no restriction, treated as
allow-everything per this project's existing convention), and it's called
directly by the site's own public page to render exactly what a normal
shopper sees — the same "prefer parsing embedded JSON over raw DOM-text
scraping" pattern this project already uses for Continente's JSON-LD, just
via a network call instead of an inline `<script>` tag.

`scraper/wegmans.py` was rebuilt on this API, replacing DOM-scraping
entirely. Three concrete benefits over the original version, not just "it
also happens to solve locations":
1. **Multi-location solved cleanly** — `STORE_NUMBERS` maps each tracked
   location's store slug straight to a real store number, no
   session/location-selector automation needed.
2. **Eliminates a disclosed risk from the original build** — whether
   "Medford" was a fixed default or IP-geolocation-based (and so might
   resolve differently from a GitHub Actions runner's IP) is now moot;
   every request specifies its store explicitly.
3. **Real promo/loyalty price fields exposed** (`price_inStoreLoyalty`,
   `discountType`) that no amount of DOM/text searching ever found — still
   not confirmed live (no product encountered had either populated), but
   now structurally ready to pick up a real example instead of silently
   missing it.

**Four tracked locations, seeded and live-scraped** (a fourth added later
the same day, per explicit instruction to add a location as geographically
distant as possible from the first two states — NY and VA — already
tracked):

| Store slug | City | Store # | Confirmed milk price | Notes |
|---|---|---|---|---|
| `wegmans-us-medford` | Medford, NY | 134 | $2.99/gal | Original build's default; renamed from `wegmans-us` (`stores.id=64` preserved, no listing references broke) |
| `wegmans-us-nyc` | Manhattan, NY | 156 | $3.99/gal | Highest of the four |
| `wegmans-us-fairfax` | Fairfax, VA | 16 | $3.69/gal | Genuine out-of-NY-state market (DC metro) |
| `wegmans-us-chapelhill` | Chapel Hill, NC | 140 | $2.49/gal | Cheapest of the four; southernmost point in Wegmans' whole footprint, maximally distant from the NY/VA locations |

**Verified live**: `wegmans-us-nyc` ran for real — **55/58 listings,
94.8% coverage** (3 fresh pork products genuinely not carried at the
Manhattan store — confirmed via the API returning `isSoldAtStore: false`,
`price_inStore: null` — the same "not every location carries every
listing" gap already documented for Auchan France's two Drive locations,
not a bug). `wegmans-us-fairfax` ran for real too — **54/58, 93%
coverage** (the same 3 pork products plus 18-count eggs not carried there
either). `wegmans-us-chapelhill` was pre-checked for full-basket availability
*before* committing to it as the fourth location (the same diligence used
for picking Fairfax) — both Chapel Hill and a second NC candidate (Wake
Forest) showed identical **50/58 (86.2%) availability** at that moment,
still comfortably above the 0.85 alert threshold; Chapel Hill was picked
as the more nationally recognizable market of the two. The real scrape run
minutes later did noticeably better — **55/58, 95% coverage**, only the
same 3 pork products missing, not the extra dairy/personal-care items the
pre-check had flagged. Worth stating plainly rather than picking whichever
number looks better: Wegmans' availability API reflects live inventory,
so a snapshot taken minutes apart can genuinely differ — the pre-check
number wasn't wrong, it just wasn't the same instant as the real run. All runs' `error_summary`
cleanly names the unavailable product by name (e.g. `"product '54042' not
carried at this store ('Wegmans Boneless Center-Cut Pork Chops')"`),
confirming the clearer error message added during the rebuild works as
intended. `wegmans-us-medford`'s listings were skipped by the existing
same-day idempotency check (already scraped once today by the original
DOM version before the rebuild) — the new code path is proven correct via
the other three locations' real runs plus `tests/test_wegmans_parsing.py`
(10 tests, all passing), since all four locations share the exact same
`fetch_listing` function, just a different `storeNumber`.

Price basis clarified as a side effect of having the raw API response:
`price_inStore`, not `price_delivery` — the latter runs consistently
~15-17% higher at every store checked, a real, new (US-specific) pricing
dimension no prior country in this project has had to account for.

## 9. Build status — scheduled matrix, 2026-07-11

Per explicit instruction, once all four locations had a real, passing
scrape run: all four (`wegmans-us-medford`, `wegmans-us-nyc`,
`wegmans-us-fairfax`, `wegmans-us-chapelhill`) added to
`.github/workflows/scrape.yml`'s matrix, `category: false` (matching
France's stores — no dynamic category-crawl scraper exists for Wegmans
either, only the fixed-basket one). They now scrape on the same twice-
daily cron as every other store (`0 6 * * *` / `0 10 * * *` UTC), with the
same idempotent same-day-retry behavior.

Not yet done: `category_weights` has no US rows (BLS quota pending reset —
see §7), so `compute.yml`'s `metrics/compute.py` run will produce
`price_snapshots` rows for the US on every scheduled scrape but no
`inflation_metrics` rows until the weights sync succeeds at least once.
