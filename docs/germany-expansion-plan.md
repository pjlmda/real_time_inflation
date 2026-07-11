# Germany Expansion Plan

Planning document, not an implementation plan — no code has been written for
this yet. Written 2026-07-11, in response to a direct request to look at
Germany next, per the country-priority order in `CLAUDE.md` (Germany → UK →
US after France) and the fact that France's remaining big chains
(Leclerc/Carrefour/Intermarché/Système U) are blocked by enterprise bot
mitigation with no further direct-scraping path forward for now.

Research below is grounded in live checks against the real sites (robots.txt
fetches, response headers, a live search-results check) done today, matching
the same "verified live, store by store" discipline used for every prior
store and for France.

---

## 1. The store landscape

### Market share (by 2025 group revenue — Statista/ESM/GroceryTradeNews)

| Group | Approx. 2025 revenue | Notes |
|---|---|---|
| Edeka | €84.7bn | Germany's #1 food retailer; owns Netto Marken-Discount |
| REWE Group | €70.6bn (>€96bn incl. all formats) | Owns Penny (discount) alongside REWE supermarkets |
| Schwarz Group | €61.3bn | Owns both Lidl and Kaufland |
| Aldi (Nord + Süd combined) | €36.9bn | Two independent regional companies, not one |
| Netto Marken-Discount | >€17bn | Part of the Edeka group, ~4,400 stores |

Edeka and REWE together account for ~47% of the market; the top four groups
combined hold ~76%. Source: [GroceryTradeNews — German Grocery Market Share 2025](https://www.grocerytradenews.com/german-grocery-market-share/), [ESM Magazine — Top 10 Supermarket Retail Chains In Germany](https://www.esmmagazine.com/retail/top-10-supermarket-retail-chains-in-germany-236817)

### Anti-bot posture — checked live today, same pattern as France

| Chain | Domain checked | Result |
|---|---|---|
| Edeka | edeka.de | **403, `server: AkamaiGHost`** |
| REWE | rewe.de | **403, `server: cloudflare`** |
| Kaufland (Schwarz Group) | kaufland.de | **403, `server: cloudflare`** |
| Aldi Süd | aldi-sued.de | **403, `server: AkamaiGHost`** |
| Netto Marken-Discount | netto-online.de | **403**, Akamai-pattern headers (`ak_p` server-timing descriptor) |
| Aldi Nord | aldi-nord.de | **200 OK** — but appears to be a marketing/flyer site (weekly offers, store locator), not a full online grocery catalog; not investigated further this pass |
| **Lidl** | lidl.de | **200 OK**, `server: myracloud` — same CDN family as Lidl France |

Every major chain except Lidl is blocked — the exact same shape of result as
France, where the four biggest chains by market share were all behind
DataDome or Cloudflare and Lidl was one of the two open doors. This isn't a
coincidence specific to France; it looks like a real pattern where Tier-1
grocery chains broadly run enterprise bot mitigation and Lidl, across at
least two markets checked so far, doesn't.

### Lidl Germany specifically — confirmed to sell real groceries online, not just weekly flyers

A live search against `lidl.de` for "milch" (milk) returned a 200 with real
EUR-priced results (51+ price mentions, hundreds of "milch" mentions in the
response) — this is a genuine online grocery catalog with real prices, not
just a digital circular. Confirmed via `lidl.de/q/search?q=milch`.

**`lidl.de/robots.txt` is nearly identical to `lidl.fr/robots.txt`** — same
disallow list shape (`*search?q=*`, `*sort=*`, `*id=*`, etc.), same
`Sitemap: https://www.lidl.de/static/sitemap.xml` pattern. This strongly
suggests Lidl runs the same underlying commerce platform across at least
these two markets (consistent with Schwarz Group's centralized IT — Lidl
operates in 30+ countries off a shared platform in practice). **Practical
implication**: whatever scraper gets built for Lidl France (still Phase 2,
not started per `docs/france-expansion-plan.md`) is a strong candidate to
transfer to Lidl Germany with comparatively small changes — same discovery
pattern (sitemap-based, since direct search-result crawling is disallowed by
robots.txt at both), likely similar or identical DOM structure. Not
confirmed yet — this needs the same live-selector verification every other
store got, not an assumption — but it changes the sequencing calculus: doing
Lidl France's scraper first has a second payoff beyond France alone.

---

## 2. What's the same as France (and Portugal)

- **Currency** — EUR, no plumbing needed, same as France.
- **Timezone** — Germany is CET/CEST (UTC+1/+2), the same offset as France
  and materially different from Portugal's WET/WEST (UTC+0/+1) — the
  per-store `timezone_id` mechanism already built for multi-country support
  (`scraper/db.py:scrape_date_for_timezone`) handles this with a config
  entry, no new code.
- **HICP weights** — Germany is an EU member reporting into the same
  Eurostat `prc_hicp_inw` dataset; `python -m weights.eurostat --geo DE`
  already works today, confirmed live (466 records fetched, real
  Germany-specific weights — e.g. Bread 8.64 vs. France's 11.31 vs.
  Portugal's 17.7 for the same COICOP code).
- **Schema** — `stores.country='DE'`, `category_weights` rows scoped to
  `country='DE'` — the exact mechanism migration 0007 built for France,
  designed from the start to not be France-specific.
- **Methodology** — same COICOP/ECOICOP taxonomy, same Jevons/weighted-mean
  formulas, no changes.

## 3. What's different / needs its own verification

- **Lidl Germany's actual DOM/selectors are not yet confirmed** — the
  robots.txt/platform similarity to Lidl France is a strong lead, not proof.
  Needs the same live Playwright spike every other store got (product page
  structure, price selectors, any location/delivery-gating mechanic like
  Auchan France had) before building anything.
- **German online grocery culture is less developed than France's** — worth
  a specific check once live selector work starts: does Lidl.de show one
  national price (like Portugal), or is pricing/availability also
  drive-point or region-gated the way Auchan France turned out to be? Not
  yet known — France's "looks simple until you actually check" lesson
  applies here too.
- **Language** — German product names/categories, new locale (`de-DE`,
  `Europe/Berlin`) — same kind of work as French curation, not a different
  kind of work.
- **Aldi Nord's real online-shop status is unconfirmed** — flagged as open
  (200 OK) but not verified to have real per-product grocery pricing the way
  Lidl does; worth a quick check before ruling it in or out, not assumed
  either way.

## 4. Recommended sequencing

1. **Finish Lidl France first** (already Phase 2 in `docs/france-expansion-plan.md`, not yet started) — given the robots.txt/platform match, building it first means Lidl Germany likely becomes a much smaller incremental effort rather than a from-scratch build, and validates or kills the "same platform" hypothesis before committing further.
2. **Lidl Germany spike** — live Playwright verification of the actual DOM/selectors and pricing model (national vs. location-gated), the same kind of spike Auchan France got, informed by whatever Lidl France's build already learned.
3. **Small pilot basket** for Lidl Germany once the spike confirms feasibility, following the same process as every other store.
4. **Not planned for now**: Edeka, REWE, Kaufland, Aldi Süd, Netto — all confirmed blocked by enterprise bot mitigation, same disposition as Leclerc/Carrefour/Intermarché/Système U in France (see `CLAUDE.md`'s anti-bot section for how a blocked-but-wanted retailer is handled — legitimate third-party data sourcing only, not bypass tooling).
5. **Aldi Nord** — worth a quick live check of whether it has real per-product online grocery pricing before deciding whether it's a second candidate; not investigated deeply enough yet to plan around either way.

## 5. Honest framing

If this plays out as expected, Germany's initial coverage would be Lidl
alone (~market share not yet quantified precisely for Lidl standalone within
Schwarz Group's combined figure, but a single mid-tier discounter, not a
market-leading share) — the same "narrower slice than Portugal's setup"
framing already applied to France's Auchan-only coverage. Worth stating
plainly in the UI once built, not implying broader coverage than exists.
