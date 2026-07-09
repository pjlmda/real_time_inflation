# France Expansion Plan

Planning document, not an implementation plan — no code has been written for
this yet. Written 2026-07-09, in response to a direct request to go deeper
than `docs/future-roadmap.md` Part 2's generic multi-country bottleneck
analysis and produce something concrete enough to actually start from:
which French stores are realistic targets, and precisely what in this
codebase is reusable versus what has to change.

Research below is grounded in live checks against the real sites (robots.txt
fetches, response headers) done today, plus a full read of the schema and
scraper code this plan has to slot into — not assumed from general
knowledge, matching this project's existing "verified live, store by store"
discipline (`seed/README.md`).

---

## 1. The store landscape

### Market share (Kantar Worldpanel, P12 2025 / November 2025)

| Chain | Market share | Structure |
|---|---|---|
| E.Leclerc | 24.9% | Independent retailer cooperative |
| Carrefour | 21.8% | Public corporation |
| Intermarché (Les Mousquetaires) | 18.1% | Independent retailer cooperative |
| Système U / Coopérative U | 12.0% | Independent retailer cooperative |
| Auchan | 8.3% | Private corporation (Auchan Holding, Mulliez family — same parent as Auchan Portugal) |
| Lidl | 8.3% | Private corporation (Schwarz Gruppe) |

These six cover roughly 93% of the market between them; the remainder is
fragmented across Casino/Géant, Cora, Monoprix, Aldi, and smaller regional
chains — not investigated further here since none individually clears ~5%.

Sources: [Statista — leading supermarkets by market share, France 2025](https://www.statista.com/statistics/535415/grocery-market-share-france/), [ESM Magazine — E.Leclerc Consolidates French Grocery Leadership With 24.8% Market Share](https://www.esmmagazine.com/retail/e-leclerc-consolidates-french-grocery-leadership-with-24-8-market-share-worldpanel-307985), [RetailDetail EU — In France, Intermarché, Carrefour, and U are the winners of 2025](https://www.retaildetail.eu/news/food/in-france-intermarche-carrefour-and-u-are-the-winners-of-2025/)

### Anti-bot posture — checked live today, and it inverts the market-share ranking

This is the single most important finding in this document. A plain
`curl` with a real desktop Chrome user-agent (no stealth, no Playwright —
the floor of what any scraper attempt would need to clear) against each
chain's actual grocery/e-commerce domain:

| Store | Domain checked | Result |
|---|---|---|
| E.Leclerc | leclercdrive.fr | **403, `X-DataDome: protected`** |
| Carrefour | carrefour.fr | **403, `server: cloudflare`** |
| Intermarché | intermarche.com | **403, `x-datadome: protected`** |
| Système U | magasins-u.com, coursesu.com | **403, `server: cloudflare`** (both domains) |
| Auchan | auchan.fr | **200 OK**, `server: dodo,local` — no WAF header on homepage or a search-results page |
| Lidl | lidl.fr | **200 OK**, `server: myracloud` (Myra Security CDN) + Kameleoon (A/B testing, not anti-bot) — no enterprise WAF header |

The four biggest chains by market share (Leclerc, Carrefour, Intermarché,
Système U — ~77% of the market combined) are all sitting behind dedicated
bot-management products (DataDome or Cloudflare) that block even a bare,
unauthenticated GET request before a single line of scraping code would
run. This is exactly the risk `docs/future-roadmap.md` Part 2 flagged in the
abstract ("Tier-1 retailers... far more likely to run enterprise bot
mitigation") — the live check just confirms it's not hypothetical for
France specifically, and identifies precisely which four are affected.

**A stealth Playwright context (this project's actual scraping tool) will
likely do somewhat better than a bare curl request** — DataDome/Cloudflare
increasingly key off TLS/JA3 fingerprints and JS-challenge execution that
curl can't pass at all, so this 403 is a floor, not necessarily the final
word. But it confirms these four have *paid for and deployed* dedicated
anti-bot infrastructure specifically because they're valuable enough
scraping targets to defend — matching the project's own stated scope
(`CLAUDE.md`: "respectful, resilient scraping... not defeating hard
security") ruling out the proxy pools/CAPTCHA-solving that would be needed
to force the issue reliably. Treat Leclerc/Carrefour/Intermarché/Système U
as **not viable for v1**, not as "try harder."

Auchan and Lidl — the two smallest of the six, 8.3% each, ~16.6% combined —
are the only two that don't show enterprise WAF resistance on a basic
check. That's a real, if narrower, foothold: comparable in scale to a
single mid-size chain, not the sweeping coverage the PT setup has with
three actively-scraped stores.

### Auchan France — live-verified 2026-07-09 via real Playwright sessions, not curl

The "same platform as Portugal" hypothesis does **not** hold: none of
`scraper/auchan.py`'s selectors (`.sales .value`, `.auc-price__stricked
.strike-through.value`, `.auc-price__promotion--show`,
`.auc-measures--price-per-unit`) matched anything on a real auchan.fr
product page, and no `demandware`/SFCC traces appeared in any network
request captured during a full page load. Auchan France needs its own
selector research from scratch — a new scraper module, not a config-only
reuse of the Portuguese one. Concretely confirmed instead:

- **Not bot-blocked**, confirmed across eleven separate live requests/
  interactions in a real (non-headless-flagged) Playwright session — no
  CAPTCHA, no DataDome/Cloudflare header, consistent with the earlier curl
  check.
- **Product URL pattern**: `/<slug>/pr-<code>`, e.g.
  `/auchan-lait-demi-ecreme-sterilise-uht/pr-C1171534`. Schema.org
  `itemtype="http://schema.org/Product"` microdata is present on search
  result tiles (rating/review count at minimum) — worth checking as a
  structured-data fallback once a delivery zone is set, the same role
  JSON-LD plays for Continente.
- **A real, new mechanic Portugal never needed: pricing is gated behind a
  delivery-zone selection.** Every product page shows an "Afficher le
  prix" (show price) button instead of a price, until a postcode/city and
  a delivery mode are chosen via a "Choisir un drive ou la livraison" modal.
  Two modes are on offer:
  - **Drive** (click & collect): shows ~15 individual physical pickup
    points near the postcode entered, each with its own "Choisir" button —
    i.e., potentially a different price at each. Not a single national
    price the way Continente/Pingo Doce/Auchan Portugal's online catalog is.
  - **Livraison à domicile** (home delivery): collapses to a single zone
    per city/postcode area (confirmed for Paris 75001 — one card, "Paris,"
    €50 minimum order) — but confirming it requires supplying a **full
    street address**, not just a postcode ("Nous avons à présent besoin de
    votre adresse complète !", confirmed live). That means a real scraper
    would need a plausible fake residential address to get past this step —
    not something this project should do.
  - **Recommendation reversed from an earlier draft of this section: use
    Drive, not home delivery.** Confirming a Drive pickup point needs only
    a postcode and picking one of the named, public pickup locations shown
    (e.g., "Auchan Drive Supermarché Buttes Chaumont - Paris") — no address
    fabrication involved, just choosing one specific, real, publicly-listed
    location's catalog. That's methodologically cleaner and a closer
    analogue to how every other store in this project already works (one
    named store, one catalog) — just narrowed to a single named Auchan
    Drive branch's catalog rather than a national one. Both options still
    mean the resulting index is disclosably local (e.g., "one Paris-area
    Auchan Drive location's prices," not "Auchan's price everywhere in
    France"), the same kind of explicit scope-narrowing this project
    already discloses for its PT simplifications (`seed/README.md`).
- **Fully confirmed end-to-end, two regions, 2026-07-09**: the full
  zone-confirmation flow (fill postcode → click the matching city
  suggestion, e.g. `"Paris 75001"` — exact text match — → click the
  `Drive` tab button → click the first plain-text `"Choisir"` button,
  `force=True` since Playwright sees it as covered by a transient overlay)
  reliably locks in a specific named Drive location for the rest of the
  browser session (confirmed via a persistent `Retrait: <location name>`
  badge in the header). Once set, `[itemprop='price']` schema.org
  microdata reliably exposes the real price on both search-result tiles
  and PDPs — a clean, structured extraction path, no fragile text-scraping
  needed (comparable to how Continente's JSON-LD fallback works).
  **Two representative, geographically distinct locations chosen**, per
  the decision to track more than one region rather than Paris alone:
  - **Paris**: postcode `75001` → "Auchan Drive Supermarché Buttes
    Chaumont - Paris"
  - **Marseille**: postcode `13001` → "Auchan Drive Supermarché Marseille
    Saint-Lazare" (~660 km from Paris, genuinely distinct region/climate/
    supply chain)

  Prices already visibly differ between the two on the same search (e.g.
  one tracked item read 1,63€ in Paris vs. 1,76€ in Marseille) — real
  regional price variation, exactly the reason to track two locations
  rather than one. Both were reached by real, public, named pickup
  locations — no fake address or personal data involved at any point.

### Lidl France — the constraint worth knowing before starting

`lidl.fr/robots.txt` explicitly disallows `*search?q=*` and other
listing/query-parameter paths, but does declare a sitemap
(`https://www.lidl.fr/static/sitemap.xml`). That rules out a direct
search-driven category crawl — the dynamic category-average crawl for Lidl
would need the sitemap-based discovery pattern this project already uses
for Pingo Doce (`config/category_urls.yaml`'s `path_prefix`/`keywords`
approach), not the direct-URL approach used for Continente/Auchan today.
Not a blocker, just a different (already-proven) pattern to reuse.

---

## 2. What's the same — reusable as-is or with config-only changes

- **Anti-bot layer** (`scraper/antibot.py`) — `RobotsChecker`, `with_backoff`,
  `detect_block`, stealth patches: entirely generic, no PT-specific logic
  anywhere in it.
- **Scraping orchestration** (`scraper/base.py`) — `BaseScraper.run()`'s
  whole control loop (idempotent skip, robots-respecting, retry/backoff,
  coverage/status calculation, block-detection, alerting triggers) is
  store-agnostic already; a French store is just a new `BaseScraper`
  subclass implementing `fetch_listing`, exactly like Continente/Auchan/
  Pingo Doce are today.
- **Store config** (`config/stores.yaml`, `scraper/store_config.py`) —
  already a config-driven per-store registry with `locale`/`timezone_id`
  fields built in specifically for this. A French store is a new YAML
  entry (`locale: fr-FR`, `timezone_id: Europe/Paris`), zero code change.
- **HICP weights fetcher** (`weights/eurostat.py`) — `fetch_weights(geo="PT")`
  already takes `geo` as a parameter; France is an EU member reporting into
  the same Eurostat `prc_hicp_inw` dataset, so `fetch_weights(geo="FR")`
  works today, unmodified. (Storing the result is a different story — see
  §3.)
- **Currency** — France uses EUR, same as Portugal. None of the
  currency-hardcoding already flagged in `docs/future-roadmap.md` (the `€`
  symbols in `HeadlineCard`/`GapCard`/`FuelPanel`, `fuel_prices.unit`
  defaulting to `'EUR/L'`) is actually a blocker for France specifically —
  this is one of the two bottlenecks that vanish for a same-currency,
  same-weights-API neighbor, exactly as that doc predicted.
- **Methodology** (`metrics/formulas.py`) — Jevons geometric mean within
  class, weighted arithmetic mean across classes, moving average,
  inflation-rate lookback: all pure math, no locale/country assumptions at
  all. Unchanged.
- **Database append-only design, `scrape_runs` observability, Telegram
  alerting** — all generic, reused without modification.
- **GitHub Actions workflow shape** — the twice-daily
  cron-with-idempotent-retry pattern (`scrape.yml`) extends naturally,
  either as new matrix entries on the existing job or (more likely, given
  the timezone issue in §3) a parallel workflow.

---

## 3. What actually needs to change

### 3.1 Schema: `inflation_metrics` has no country dimension — this is a real blocker, not just extra work

```sql
create table inflation_metrics (
    ...
    dimension text not null check (dimension in ('overall', 'category', 'subcategory', 'store', 'brand')),
    dimension_value text not null,
    ...
);
```

ECOICOP/COICOP codes are the *same international taxonomy* in France as in
Portugal — `01.1.1.3` means "Bread" in both countries. If a French Bread
category index and a Portuguese Bread category index both try to write
`dimension='category', dimension_value='01.1.1.3'` for the same
`as_of_date`, they collide on the same row. `dimension='overall',
dimension_value='ALL'` collides even more directly — there's currently no
way to represent "Portugal's overall index" and "France's overall index" on
the same day at all. This needs a `market` (or `country`) column added and
folded into the row's identity (uniqueness constraint), not just a nice-to-have —
**the fixed-basket compute job would silently overwrite one country's
numbers with the other's without it.**

### 3.2 Schema: HICP weights are country-specific, but `categories.hicp_weight` is a single column

```sql
create table categories (
    ...
    ecoicop2_code text not null unique,
    ...
    hicp_weight numeric(7, 4),
    weight_year smallint
);
```

France's HICP weight for Bread is a different number from Portugal's — same
code, different weight. The current design (one `categories` row per code,
one weight column on it) can't hold two countries' weights simultaneously.
Recommended fix: keep `categories` as the shared, country-agnostic
code/name taxonomy (it genuinely is shared — COICOP is an EU-wide
standard), and move `hicp_weight`/`weight_year` out into a new table keyed
by `(ecoicop2_code, country)`, e.g. `category_weights`. `hicp_weights_cache`
(currently `ecoicop2_code, weight_year, weight, fetched_at, source_dataset`
— also no country column) needs the same addition, since it's meant to be
an audit trail of every fetch and would otherwise be ambiguous about which
country a cached row belongs to. `weights/eurostat.py:upsert_weights()`
needs a `country` parameter threaded through both writes.

### 3.3 `lisbon_scrape_date()` is hardcoded to Europe/Lisbon and used globally, not per-store

```python
# scraper/db.py
LISBON_TZ = ZoneInfo("Europe/Lisbon")

def lisbon_scrape_date() -> str:
    return datetime.now(LISBON_TZ).date().isoformat()
```

This single function determines `scrape_date` and the same-day idempotency
boundary for **every store**, not per-store despite `StoreConfig` already
carrying a `timezone_id` field (used only for the browser context's
timezone spoofing today, not for this). Portugal is WET/WEST (UTC+0/+1);
France is CET/CEST (UTC+1/+2) — **one hour ahead year-round**, not a DST
quirk that happens to align. A French store would inherit Portugal's
midnight as its day boundary, which is subtly wrong (a scrape landing at
23:30 Lisbon time — 00:30 Paris time — would get dated to the wrong day
for France's own calendar, and the "already captured today"/"blocked
earlier today" idempotency checks would be evaluating the wrong day's
cutoff for a French store). Needs to become parameterized by store/market
rather than a single global constant — a real, if small, code change to
`scraper/db.py`'s `lisbon_scrape_date()`/`is_same_lisbon_day()` and every
call site currently assuming there's only one relevant timezone.

### 3.4 Frontend and API have no market concept at all

`web/api/db.py`'s every query (`get_categories`, `get_stores`,
`get_latest_overall`, `get_series`, ...) has no country/market filter —
it's implicitly "the one market this deploys for." Once `inflation_metrics`
gains a `market` column (§3.1), every one of these needs a market parameter
threaded through, and the Next.js dashboard needs either a market switcher
or a decision to run separate deployments per market. Not attempted in this
plan — flagged as the natural next question once the backend actually has
two markets' data to serve.

### 3.5 New, from scratch: the basket itself

Everything in §2 is code/schema. The actual basket — curated French
products, real EANs, verified price-per-unit parsing per store, category
listing-page URLs for the dynamic crawl — is 100% new work, store by store,
the same live-verification-heavy process `seed/README.md` already documents
for Portugal's three stores. This is `docs/future-roadmap.md` Part 2's
"solo-maintainer time... least fixable by better architecture" bottleneck,
restated concretely: there is no shortcut for this part regardless of how
much of the surrounding code is reused.

### 3.6 Category coverage subset may need re-checking, not assuming

The plan's PT scope is COICOP divisions 01, 02.1, 05.6.1, 12.1.x
("supermarket-buyable"). This is very likely still the right subset for
France's supermarkets too, but should be verified rather than assumed once
real product curation starts — French retailers may carry (or not carry)
slightly different category ranges online (e.g., alcohol/tobacco
regulatory differences, personal-care assortment differences).

---

## 4. Recommended sequencing

1. **Phase 0 — schema fork: done, 2026-07-09.** Migration `0007_multi_country_support.sql` applied to the live database (additive-only: `inflation_metrics.country` default `'PT'`, new `category_weights` table backfilled from the existing PT weights, `hicp_weights_cache.country`). Every consumer updated in the same pass and verified against live production data:
   - `metrics/compute.py`/`metrics/category_compute.py`: rewritten to group stores by country and run the whole overall/category/store aggregation per country — this closes a real bug the migration exposed (`fetch_basket_rows`/`fetch_category_observations` previously had **no country filter at all**, so a French store's listings would have silently blended into Portugal's "overall" index the moment one was added).
   - `web/api/db.py`: every `inflation_metrics`/weight query now explicitly pinned to `ACTIVE_COUNTRY = "PT"` (the live dashboard has no market switcher yet) rather than reading whatever country happens to be in the table.
   - `weights/eurostat.py`: `upsert_weights()` takes a `country` param and writes into `category_weights`; `python -m weights.eurostat --geo FR` now works for a future country with no further code change.
   - `scraper/db.py`: `lisbon_scrape_date()`/`is_same_lisbon_day()` renamed to `scrape_date_for_timezone(timezone_id)`/`is_same_day(iso_timestamp, timezone_id)` and `SupabaseWriter` now takes a `timezone_id` (from `StoreConfig`, already per-store) instead of a hardcoded Lisbon constant.
   - 94 tests passing (6 new), plus live read-only verification against production Supabase.
   - **Deliberately not done yet**: `categories.hicp_weight`/`weight_year` (the old columns) are still present but unused by any code path — a follow-up migration should drop them now that everything reads from `category_weights` instead, once this is deployed and confirmed stable.
2. **Phase 1 — Auchan France: done, real data flowing, 2026-07-10.** `scraper/auchan_france.py` implements the full confirmed flow (session-level Drive-location confirmation via a `_build_context` override, price extraction via `[itemprop='price']` microdata, price-per-unit via a text-pattern match since that element has no distinguishing class). Registered in `scraper/run.py`'s `SCRAPERS`; `auchan-fr-paris`/`auchan-fr-marseille` both `active: true` in `config/stores.yaml` and seeded into the live `stores` table with `country='FR'` (not yet in `.github/workflows/scrape.yml`'s matrix — manual-run only for now). Along the way, fixed a real bug in `seed/stores.py:load_store_rows()` — it hardcoded `country="PT"` for every store regardless of `config/stores.yaml`, which would have silently mis-seeded these as Portuguese.

   **Pilot basket curated and scraped live**: 5 products across 5 categories (rice, bread, cheese, eggs, fresh fruit — real EANs pulled from each PDP's "Réf / EAN" field), each with a listing at both locations. `python -m scraper.run --store auchan-fr-paris/-marseille --mode basket` both ran for real: **5/5 listings, 100% coverage, at both locations.** Confirmed genuine regional price variation on the same day — e.g. rice 2.24€ in Paris vs. 2.10€ in Marseille, eggs 1.76€ vs. 1.65€ — exactly the reason two locations are tracked instead of one. 103 tests passing.
   - **Not yet confirmed live**: promo/regular-price detection (`is_promotion`/`regular_price` currently default to "no promotion" — no promoted product was encountered during research; needs checking against a real promo before it can be trusted, same caveat Auchan Portugal's own selectors originally had).
   - **Next**: grow the basket beyond this 5-product pilot (more categories, more products per category), add these two stores to `scrape.yml`'s matrix once satisfied with stability, run `metrics/compute.py` to confirm a real French index value comes out the other end.
3. **Phase 2 — Lidl France**, using the sitemap-based category-discovery pattern already proven for Pingo Doce (§1, Lidl's robots.txt disallows search-based discovery).
4. **Phase 3 — full basket curation** for both stores once Phase 1 confirms the pipeline works, following the same category-by-category, live-verified process as every PT basket-growth round.
5. **Explicitly not planned**: Leclerc, Carrefour, Intermarché, Système U — revisit only if the project's scope deliberately changes to accept proxy/anti-bot escalation costs, which `CLAUDE.md`'s stated scope currently rules out.

## 5. Honest framing for the result

Even a fully-executed Phase 1–4 gives a France index built from two chains
covering ~16.6% of the market by revenue share — a narrower retailer mix
than Portugal's three-store, much-friendlier setup. That doesn't invalidate
the methodology (HICP-style indices don't require exhaustive retailer
coverage, just a representative, consistently-sampled basket), but it
should be labeled honestly in the UI the same way the "supermarket
HICP-comparable, not full HICP" distinction already is for Portugal — a
France index from Auchan+Lidl alone is a narrower slice of the market than
its Portuguese counterpart, and that's worth saying plainly rather than
implying parity.
