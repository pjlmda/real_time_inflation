# Future Roadmap: Personalized Weights & Multi-Country Expansion

Planning document, not an implementation plan — no code changes are proposed
here; this is groundwork for two future-development directions the user
asked about. Written 2026-07-09, after Phase 3 (web app) and the second
basket-growth round were both live and verified.

---

## Part 1 — User-customizable category weights ("my personal inflation rate")

**Status: v1 shipped 2026-07-09** at `/personalize` (`web/app/personalize/`), built exactly along the lines recommended below — client-side computation, URL-encoded shareable weights, no auth, no new table. What's described in this section as "recommended architecture" is what actually got built; see `docs/system-overview.md` §3.11 and §14 for the as-built writeup and what's still missing (preset profiles, `localStorage` persistence — both still just ideas, not built).

### Why this is worth building

The headline number is currently a weighted average using **official HICP
weights** — Portugal's average household's spending pattern. A real
household rarely matches that average: a vegetarian household spends
nothing on meat, a family with young children over-indexes on dairy and
eggs, a budget-conscious shopper cares more about the cheapest-tier products
than the mid-market ones the fixed basket happens to include. Letting users
adjust category weights turns "here's Portugal's grocery inflation" into
"here's *your* grocery inflation" — a real differentiator, since most public
inflation trackers only ever show the official aggregate.

### Recommended architecture: compute it client-side, not server-side

This is the single most important design decision, because it changes the
feature from "a few days of frontend work" into "a new user-accounts
subsystem," depending on which way it goes.

**The insight**: `inflation_metrics` already stores a daily `index_value`
per ECOICOP category (`dimension='category'`), going back to when each
category was added. The overall index is *already* just
`metrics.formulas.weighted_overall_index()` — a weighted arithmetic mean of
those per-category values. A "personalized" index is the exact same
function, called with the user's weights instead of `hicp_weight`. Nothing
about that requires new backend computation, storage, or a user-accounts
system — it can run entirely in the browser, on data the API already
returns.

**Recommended shape**:
1. A new page (or section of the existing dashboard) with one slider/input
   per ECOICOP category, pre-filled with the real HICP weights as the
   starting point (so "reset to official" is just "reset to defaults").
2. The frontend fetches each category's current index (already available
   via `/api/categories`) and, for the trend chart, each category's daily
   series (`/api/inflation/series?dimension=category&value=<code>` — see
   note below on batching this).
3. As the user drags a slider, recompute the weighted average **in
   JavaScript**, live, no network round-trip per change.
4. Encode the weight vector in the URL's query string
   (`?w=01.1.1.3:0.15,01.1.4.1:0.30,...`) rather than a database row. This
   makes a personalized view **shareable via a plain link** with zero
   backend storage and zero auth — "here's my basket, see for yourself" is
   just a URL.

**The one plausible backend addition**: fetching 19 separate category time
series (one HTTP call each) to build the personalized trend chart is
wasteful. A small new endpoint or query-param extension —
`/api/inflation/series/bulk?dimension=category` returning every category's
series in one response — would be worth adding. Everything else needs no
backend change at all.

**A nice product idea that falls out of this for free**: preset profiles.
"Vegetarian household," "Family with young children," "Budget-conscious"
(this one maps directly onto the cheapest-tier products just added to the
basket — a household that mostly buys the cheap-tier items could use a
weight profile that leans toward those specific listings' categories) could
ship as one-click starting weight vectors, with manual fine-tuning after.
This connects two otherwise-separate pieces of work (basket-growth's
cheapest-tier products, and this feature) into one coherent story.

**Framing risk — the one thing to get right**: once a user changes weights,
the result is explicitly *not* HICP-comparable anymore. The whole project's
credibility rests on being careful about this exact distinction (see
`docs/system-overview.md` §6 on "supermarket HICP-comparable, not full
HICP"). The UI needs to make unmistakably clear that a personalized number
is a personal estimate, styled/labeled distinctly from the official-comparable
headline, the same care already given to distinguishing `fixed_basket` from
`category_avg`.

**What this does *not* need**: a migration, a new `index_family`, user
accounts, or a database table. If long-term persistence ("save my named
profile across visits") is wanted later, that's a small addition
(`localStorage` first; a real accounts system only if cross-device sync
becomes a real ask) — but it's not a prerequisite for shipping v1.

**Rough effort**: mostly frontend (a components + client-side math, reusing
the exact formula already implemented and tested in `metrics/formulas.py` —
just reimplemented in TypeScript, or exposed via one more tiny API call if
reuse-not-reimplement is preferred) plus one optional bulk-series endpoint.
Genuinely small relative to everything else built this session.

---

## Part 2 — Multi-country expansion (France, Germany, UK, US)

### The honest bottleneck ranking

1. **Anti-bot difficulty at bigger retailers — likely the hardest blocker.**
   Portugal's three stores all turned out to be relatively
   scraping-friendly (Salesforce Commerce Cloud, permissive `robots.txt`,
   no aggressive bot mitigation encountered). That was not a given — it was
   verified live, store by store, this session and prior ones. Tier-1
   retailers in bigger markets (Walmart, Kroger, Tesco, Sainsbury's, REWE,
   Carrefour, Leclerc) are far more valuable scraping targets — used by
   price-comparison sites, hedge funds doing alternative-data research, and
   competitors — so they're correspondingly more likely to run enterprise
   bot mitigation (Akamai, PerimeterX/HUMAN, Cloudflare Enterprise,
   DataDome). The project's stealth approach (`scraper/antibot.py`'s
   `navigator.webdriver` patch, jittered delays, persistent context) was
   built for, and only verified against, mid-size Portuguese chains. It may
   simply not work against Tier-1 US/UK/DE/FR retailers — and the project's
   own stated scope (`CLAUDE.md`: "respectful, resilient scraping... not
   defeating hard security") rules out escalating into the countermeasures
   (residential proxy pools, CAPTCHA-solving services) that would be needed
   to force the issue. Practical consequence: expansion may need to target
   second-tier/regional chains in each new market rather than the biggest
   players, the same way Pingo Doce and Auchan were reasonable Portuguese
   choices rather than, say, a hypothetical harder-to-scrape rival.

2. **Solo-maintainer time — scales linearly and painfully, with no
   tooling shortcut.** Every new country roughly multiplies: stores to
   onboard and keep working, scrapers that can silently break on a
   redesign (already happened twice within Portugal alone — Continente's
   selectors needed rework, Auchan's promo selector was flatly wrong for
   months until caught live this session), currencies/languages/legal
   regimes to track, and official statistical sources to keep in sync. The
   curation work for Portugal's ~99 products across 3 stores took
   substantial hands-on, live-verified effort across many sessions — that
   cost repeats per country, in an unfamiliar language each time. This is
   the least "fixable by better architecture" bottleneck of the four.

3. **The US has no clean HICP-equivalent — a methodology problem specific
   to the US.** France and Germany are both EU members already covered by
   the *same* Eurostat `prc_hicp_inw` dataset this project already calls —
   `weights/eurostat.py` would need only a `geo=FR`/`geo=DE` parameter
   change to pull real, programmatic weights for either country, with
   effectively no new code. The UK, post-Brexit, no longer reports into
   that framework — the ONS publishes its own CPIH/CPI weights via a
   different API with a different classification structure, needing a new
   `weights/ons.py`-style fetcher, a real but bounded cost. The US
   publishes CPI via the BLS using its own item-category classification,
   not COICOP — there's no clean, fine-grained, programmatic crosswalk to
   ECOICOP v2 leaf classes the way Eurostat provides for EU members. This
   directly undermines the project's core differentiator (methodologically
   aligned with, and comparable to, an official published index) for a US
   version specifically — it would have to be reframed as "US CPI-comparable,
   approximately," with real fidelity loss versus the current PT framing.

4. **Currency and locale plumbing — real, bounded engineering work.**
   France and Germany use EUR, so nothing currency-related changes for
   them. The UK (GBP) and US (USD) would require currency-awareness that
   doesn't exist today — `€` is hardcoded in frontend components
   (`HeadlineCard`, `GapCard`, `FuelPanel`), and `fuel_prices.unit` defaults
   to `'EUR/L'`. Every scraper is also locale-specific by construction —
   decimal separators (PT/DE use commas, UK/US use periods), unit
   abbreviations, and all product-name research have to be redone in the
   local language regardless of currency. This is normal, scoped work, not
   a fundamental limiter.

5. **Infrastructure cost — the least concerning, but not free forever.**
   GitHub Actions' free tier scales fine with more scraping jobs (unlimited
   minutes on a public repo); the real friction is schedule/secrets/alerting
   complexity, not compute cost. Supabase's 500 MB free tier is a real
   ceiling worth tracking — the original single-country plan estimated
   ~175k snapshot rows/year (`inflation-tracker-plan.md` §10); 4–5 more
   countries, each with their own basket and stores, could plausibly
   multiply total row volume several-fold well within a year or two,
   likely forcing a paid tier sooner than a Portugal-only deployment would.
   If harder markets do require proxy/anti-bot escalation (see #1), that
   would be the project's *first* recurring monetary cost — `PROXY_URL`
   exists today purely as an "off by default, last resort" escape hatch,
   and multi-country expansion into defended markets could turn it from
   last-resort into baseline requirement.

### If pursued, a sensible sequencing

**France and Germany are the natural next step, not the UK or US** —
same currency (no plumbing), same official weights API (near-zero new
code for that piece), broadly comparable EU legal posture. That said,
"same currency and weights API" only removes two of the five bottlenecks
above — anti-bot difficulty and maintainer time still have to be evaluated
per retailer, the same way each Portuguese store was individually verified
live rather than assumed. The UK is a moderate step up (new weights source,
new currency, comparable-but-diverging legal framework post-Brexit). The US
is the largest leap on every axis at once — no clean official-data mirror,
new currency, and very likely the most heavily bot-defended major retailers
of the four.

### What would need to change structurally in the codebase

Not attempted here in detail, but worth flagging as a real fork: today,
`stores.country` exists as a column but the whole system otherwise assumes
Portugal/EUR/pt-PT implicitly in dozens of places (scraper locale/timezone
config, currency symbols, weight-fetcher's `geo` parameter, category
curation itself). A genuine multi-country version would want "market"
(country + currency + language) promoted to a first-class dimension
threaded through the schema, the weights fetcher, and the frontend, rather
than PT being hardcoded and other countries bolted on per-instance. That's
itself a non-trivial refactor worth scoping deliberately before the second
country is added, not discovered incrementally while adding it.
