# United States Expansion Plan

Research-only document, written 2026-07-11 in response to a direct request
to study the US next (UK explicitly deferred). No code has been written —
this mirrors the same live-verification-heavy research phase every other
country got before any scraper was built, including the ones that ended up
shelved (`docs/germany-expansion-plan.md`).

**Bottom line up front**: the sourcing side looks at least as hard as
Germany's — of 16 chains checked live, the top 4 by market share
(Walmart, Kroger, Costco, Target) are all confirmed behind enterprise-grade
bot mitigation, and the one structurally promising lead (Aldi US) explicitly
disallows all crawling in its own `robots.txt`, which rules it out under
this project's own non-negotiable "respect robots.txt" rule regardless of
whether it's technically scrapable. Two chains (H-E-B, Wegmans) are
inconclusive and would need more investigation before a yes/no call. On the
weights side, this doc **corrects an assumption in `CLAUDE.md`**: a real,
official BLS crosswalk to COICOP/HICP does exist (not "no clean crosswalk"),
refreshed annually — but with its own real access caveats (see §3). Net: not
a clean "no" the way Germany turned out to be, but not a green light either.
Recommend more targeted investigation (H-E-B/Wegmans depth, the BLS weights
API question) before any code, not a decision to build or to shelve yet.

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
| **H-E-B** | `robots.txt` is genuinely permissive (`Disallow: /category/*?*` and `/cart/` only). But every real page load (homepage and search) returns a consistent, tiny 489-character body with no title and no visible `$` — looks like a client-rendered shell that isn't populating, possibly a silent bot-detection response rather than a real block page. **Inconclusive** — would need more investigation (longer render wait, checking for a JS challenge specifically) before ruling in or out. |
| **Wegmans** | `robots.txt` explicitly says `Allow: /` for all bots. `domcontentloaded` loads fine (real title "Wegmans", 6KB of real content) but a `networkidle` wait times out — likely a chatty SPA with constant background polling rather than a block, but not confirmed either way. **Inconclusive**, second-strongest remaining lead after H-E-B. |

Pattern: the same shape as France and Germany — the biggest chains by
market share run enterprise-grade bot mitigation (Akamai at Costco,
PerimeterX at Target, Cloudflare at WinCo, unnamed challenge systems at
Walmart/Meijer), and the two genuinely open doors found so far (H-E-B,
Wegmans) are both unconfirmed rather than clean passes — unlike Lidl in
France/Germany, which was unambiguously reachable on the first real check.

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
- **What's still unconfirmed**: whether the actual *expenditure weights*
  (the "relative importance of components" figures — the BLS analogue of
  Eurostat's `hicp_weight`) are queryable through `api.bls.gov`'s
  time-series endpoints, or only published as the (Akamai-blocked, and see
  next point) annual `.xlsx`/PDF report. This needs to be resolved with a
  real, live check against the API's series catalog before any
  `weights/bls.py` gets written — not assumed either way.
- **Publication of the R-COICOP `.xlsx` was paused in December 2024**,
  per BLS's own site, "to be resumed when resources are available" — a
  live currency risk. This project's whole weights model depends on a
  yearly-refresh source that's actually maintained; a paused research
  series is a real reason for caution, not just an inconvenience.

**Net on weights**: less bleak than `CLAUDE.md` currently states — there is
a real, official crosswalk, and BLS does run a genuine, no-scraping-needed
public API — but "does the API expose the weight figures specifically, and
is the underlying research series still being maintained" are both open,
unresolved questions that need their own live-verification pass before
this stops being a gap.

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

1. **Resolve the `api.bls.gov` weights-granularity question** — confirm
   live whether relative-importance/expenditure-weight figures are
   available through the JSON API, or only through the paused/blocked
   `.xlsx` report. This determines whether `weights/bls.py` is even
   buildable the way `weights/eurostat.py` is.
2. **Deeper investigation of H-E-B and Wegmans** specifically — both
   passed the robots.txt check and a basic reachability check but neither
   was conclusively confirmed to have a real, non-blocked, per-product
   catalog the way Lidl was for France/Germany within a single research
   pass. This is the most promising open thread, not a dead end — the
   blank-shell H-E-B result and the Wegmans `networkidle` timeout both need
   a dedicated DOM/pricing spike (longer render waits, checking a real
   product-detail page directly rather than just home/search) before
   either gets ruled in or out.
3. **A live single-day, multi-city price comparison** on whatever
   chain(s) survive steps 1-2, mirroring the Auchan France Paris/Marseille
   discovery, to settle whether US online grocery pricing is national or
   regional before committing to a one-location-per-store or
   multiple-locations-per-store model.
4. **Re-verify the "supermarket-buyable" COICOP subset** against whatever
   chain(s) survive, the same live-verification discipline as every
   category-growth round in `seed/README.md`.

## 5. Honest framing

This is not a "Germany" (a clean no, exhausted and shelved) and not a
"France" (real chains, real access, straightforward build once found). It
sits in between: genuine bot-mitigation coverage across the market-leading
chains that's at least as heavy as Germany's, one clean disqualification by
policy (Aldi US's own `robots.txt`), and two unresolved leads (H-E-B,
Wegmans) that would need real spike work — the same kind of live DOM/price
verification every other store in this project got — before a genuine
build-or-shelve call can be made. The weights/methodology side is better
than `CLAUDE.md` currently states, but not solved: a real official
crosswalk exists, refreshed annually, but whether it's reachable
programmatically without hitting Akamai, and whether it's still being
maintained past its December 2024 publication pause, are both open,
unresolved questions.
