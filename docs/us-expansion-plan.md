# United States Expansion Plan

Research-only document, written 2026-07-11 in response to a direct request
to study the US next (UK explicitly deferred). No code has been written —
this mirrors the same live-verification-heavy research phase every other
country got before any scraper was built, including the ones that ended up
shelved (`docs/germany-expansion-plan.md`).

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
`CLAUDE.md`'s prior "no clean crosswalk" claim) — and a second pass
localized exactly where the wall is: `api.bls.gov`'s JSON API works,
unauthenticated, confirmed live; but **both** `www.bls.gov` (the site
hosting R-COICOP/R-HICP `.xlsx` files) **and** `download.bls.gov` (BLS's
separate bulk flat-file service) are Akamai-blocked, and `download.bls.gov`'s
block page explicitly states BLS's own anti-automation policy in writing.
Whether the specific weight/"relative importance" figures are exposed
through the open `api.bls.gov` JSON endpoint (BLS says they should be, as
"aspect metadata," added November 2024) is the one remaining unconfirmed
step — needs a registered API key to test the exact request format. Net:
Wegmans is a genuine, promising candidate worth a real DOM/pricing spike
next; the weights side needs one more concrete API test, not abandoned
research.

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
- **What's still unconfirmed**: whether that same aspect/relative-importance
  data is retrievable through the *other* channel BLS names —
  `api.bls.gov`'s JSON time-series endpoint, already confirmed live and
  open for regular index values (§ above). The aspect-metadata request
  format wasn't tested against the live API in this pass (BLS's own
  documentation suggests it may require a registered v2 API key, which
  wasn't obtained here) — this is the one concrete, well-scoped next step,
  not an open-ended unknown.
- **Publication of the R-COICOP `.xlsx` was paused in December 2024**,
  per BLS's own site, "to be resumed when resources are available" — a
  live currency risk. This project's whole weights model depends on a
  yearly-refresh source that's actually maintained; a paused research
  series is a real reason for caution, not just an inconvenience. This
  doesn't affect the aspect-metadata/relative-importance data specifically
  (a separate, apparently still-active data product, added in November
  2024, after the R-COICOP pause) — worth keeping the two straight rather
  than treating one pause as evidence about the other.

**Net on weights**: better than `CLAUDE.md` previously stated — there is a
real, official crosswalk, BLS runs a genuine, no-scraping-needed public API
that's already confirmed live and working, and the specific place the
weight data is blocked (`bls.gov`, `download.bls.gov`) is now precisely
identified rather than a vague "the whole site might not work." The one
remaining unresolved step — register a free `api.bls.gov` v2 key and test
the aspect-metadata request format against a real food-category series —
is small, concrete, and was the natural next action, not attempted in this
pass for lack of a registered key.

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

1. **Register a free `api.bls.gov` v2 API key and test the aspect-metadata
   request format** against a real food-category series (e.g. the "food
   at home" strata) to confirm relative-importance/weight figures are
   actually retrievable that way. This determines whether `weights/bls.py`
   is buildable the way `weights/eurostat.py` is — the one concrete,
   well-scoped step left on the weights side.
2. **A proper DOM/pricing spike on Wegmans**, the same discipline every
   other store in this project got before a scraper got written: confirm
   the store-location selector flow end to end (does explicit ZIP/store
   entry work reliably, or does it silently fall back to IP geolocation
   that might behave oddly from a GitHub Actions runner's IP?), confirm
   price-block selectors are stable across multiple real products, and
   check for a promo/regular-price pattern the way every other store's
   spike did.
3. **A live single-day, multi-city price comparison** on Wegmans — it's
   regional (Northeast US: NY, PA, NJ, MA, VA, MD, NC, DC and others), so
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
on Wegmans alone would start narrower than Portugal's three-store setup,
the same "narrower slice" framing already applied to Auchan-only France —
worth stating plainly, not implying broader US coverage than exists. This
is closer to a "France" outcome (a real, reachable chain found, ready for
a proper build spike) than a "Germany" one (exhausted, shelved) — though
one more concrete step (the BLS weights-API key test) is still open before
committing to a full build, since the whole point of this project's
methodology is HICP-comparable weights, not just any price index.
