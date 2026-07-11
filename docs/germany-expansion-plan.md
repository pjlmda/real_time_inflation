# Germany Expansion Plan

**Status (2026-07-11): shelved.** Twelve German chains were checked live;
none is currently viable. Lidl Germany looked like the strongest lead (not
bot-blocked, same commerce platform as Lidl France) and a full scraper was
even built and pilot-tested against it, but was abandoned after confirming
its online catalog doesn't sell real groceries at all (see §1b). No other
chain checked cleared the bar either — see §1c for the full list. Do not
restart Germany work from scratch; read §1b/§1c first so this research isn't
repeated. Revisit only if a specific chain's situation has changed (new
online shop launch, a chain not yet checked, or a legitimate third-party
data-provider relationship per `CLAUDE.md`'s anti-bot sourcing policy).

Research below is grounded in live checks against the real sites (robots.txt
fetches, response headers, live search/navigation/DOM checks) done on
2026-07-11, matching the same "verified live, store by store" discipline used
for every prior store and for France.

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

### Lidl Germany — platform match confirmed, but the online catalog is not groceries (§1b)

The platform-match hypothesis below was correct: `lidl.de` runs the identical
Nuxt commerce platform as `lidl.fr` (same `data-gridbox-impression` JSON
tile structure, same PDP URL pattern `/p/<slug>/p<id>`, same numeric food
category ID `s10068374` at both `lidl.fr/c/manger-boire/` and
`lidl.de/c/essen-trinken/`, same two real bugs reproduced identically: the
`RobotsChecker` SSL/myracloud-CDN issue and the `friendlyCaptchaSitekey`
false-positive block). `scraper/lidl_france.py`'s bug fixes both carry over
directly if Lidl Germany is ever revisited.

**But the earlier "milch returns real EUR-priced results" finding above was a
false signal.** That check was a raw `curl`/regex substring count against
unrendered HTML — it picked up incidental mentions of "Milch" in allergen
disclosures and unrelated product descriptions (e.g. "enthält Milch"), not
actual milk cartons for sale. A rigorous re-check with real Playwright
sessions, structured `data-gridbox-impression` JSON parsing (the same method
that successfully curated all 12 Lidl France products), told a completely
different story:

- **30 grocery-staple search terms, two rounds** (`milch`, `brot`, `nudeln`,
  `reis`, `kaese`, `eier`, `huehnerbrust`, `rindfleisch`, `schweinefleisch`,
  `joghurt`, `olivenoel`, `apfel`, `karotten`, `duschgel`, `lachs`,
  `thunfisch`, then more precise phrasing: `vollmilch`, `toastbrot`,
  `spaghetti nudeln`, `basmati reis`, `gouda scheiben`, `eier
  freilandhaltung`, `haehnchenbrust filet`, `rinderhack`, `schweinefilet`,
  `naturjoghurt`, `olivenoel nativ`, `aepfel`, `duschbad`) — every one
  returned zero or near-zero real grocery products. Results were
  overwhelmingly kitchen appliances (Milchaufschäumer, Eierkocher,
  Reiskocher), camping/fishing gear, and clothing.
- **9 more searches for shelf-stable pantry categories** (`kaffee`,
  `schokolade`, `bier`, `konserven`, `chips`, `tee`, `cola`, `nudelsauce`,
  `honig`) — same result: coffee machines, chocolate-flavored liqueur,
  cookware, a T-shirt brand called "Tee", a Coca-Cola-branded popcorn
  maker. Only `bier` returned real product (beer kegs) and only because
  it's alcohol, not because the category itself worked.
- **`wein rot`** (red wine) was the *only* search term across both rounds
  (39 terms total) that reliably returned real, relevant grocery products
  in both passes.
- **Direct navigation to Lidl's own confirmed nav destinations** settled
  it: the `essen-trinken` top-nav link no longer even resolves to a
  category page (it now serves an "Aktionsprospekt" flyer redirect, 0
  product boxes). The real food-adjacent hub pages from Lidl's own header
  nav — `/h/obst-gemuese/` (fruit & veg), `/h/suesswaren-snacks/`
  (confectionery & snacks), `/h/getraenke/` (beverages) — return almost
  nothing: one seasonal chestnut snack at €19.99, one liqueur mislabeled as
  confectionery, and only alcoholic drinks (sangria, cider, spritz) under
  "beverages" — no water, juice, or soda.

**Conclusion**: `lidl.de`'s online shop is a rotating "Aktionsware" (weekly
non-food specials: tools, appliances, clothing, toys) plus a wine/spirits/
beer shop. It does not sell day-to-day groceries online at all — those are
physical-store-only in Germany. This is a real difference from Lidl France,
whose online shop does carry a genuine food catalog (confirmed, 12 real
products curated — see `docs/france-expansion-plan.md`). **Lidl Germany is
not a viable data source for a supermarket-HICP-comparable index** — a
wine/beer/spirits-only basket would cover just COICOP 02.1.x, none of the
food divisions (01.x) the project is meant to track, and would be
misleading to present as "Germany's grocery inflation."

### Other German chains checked (§1c) — none viable

| Chain | Result |
|---|---|
| Edeka, REWE, Kaufland, Aldi Süd, Netto (Edeka's) | 403, Akamai/Cloudflare — bot-blocked |
| Netto-online.de | 403 — bot-blocked |
| Aldi Nord | 200 OK, but zero e-commerce anywhere on the site — no `€` sign on its "Sortiment" (assortment) or "Angebote" (offers) pages, no cart, no PDPs. Pure marketing/circular site. |
| Norma | 200 OK, but its offers page is an image/flyer-style circular — no structured text prices found. |
| Globus | Redirects to a store-locator page (`/maerkte.php`), not a shop. |
| tegut | Its "Online Shop" nav link (`/onlineshop.html`) goes straight to an Amazon.de-partnership page ("Der tegut... Amazon Online Shop") — no independent catalog. |
| Penny | The one partial positive: `/angebote/` (weekly offers) has real structured prices via the same `data-gridbox`-style tile JSON pattern (avocado €0.66, ground beef €7.49, peaches €1.49, real COICOP-mappable categories). **But** the product tiles carry `data-prevent-navigation="true"` — they're JS-only overlay triggers, not real pages; the URL shown in the DOM (e.g. `/angebote/obst-und-gemuese/avocado`) 404s on direct navigation. This project's scrapers are all built around fetching a stable per-listing URL (`page.goto(listing.url)`); Penny has none. It would need a different scraper architecture (extract straight from the listing/category page's embedded data), and even then it's a **weekly-rotating circular, not a persistent catalog** — most curated items likely wouldn't exist under the same URL/slug the following week, breaking the price-history continuity the whole index depends on. Not pursued for now; flagged here as the one lead worth revisiting if Germany comes back into scope. |

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

## 4. Outcome and what would change this

Germany is shelved, not permanently ruled out. What it would take to revisit:

- **A German chain not yet checked** launches or is found to run an
  independent, unblocked, persistent-catalog online shop (12 chains covering
  Edeka, REWE, Kaufland, Aldi Nord/Süd, Lidl, Penny, Netto (both), Norma,
  tegut, and Globus are already ruled out — see §1b/§1c — so this would need
  to be a smaller/regional chain, e.g. Combi, Feneberg, Marktkauf, Bio
  Company, none of which have been checked yet).
- **Penny's architecture changes**, or someone builds the non-standard
  extract-from-listing-page scraper and accepts the weekly-rotation
  continuity risk (§1c) — this is the one concrete, partially-scoped path
  already identified.
- **A legitimate third-party data-provider relationship** materializes for
  one of the blocked Tier-1 chains (official partner API, licensed panel
  data like Kantar/NielsenIQ) — per `CLAUDE.md`'s anti-bot sourcing policy,
  never a commercial anti-detection/scraping-API vendor.

No code exists for Germany today — `scraper/lidl_germany.py` was never
created; only research and the (unused) confirmation that `lidl_france.py`'s
bug fixes would carry over if Lidl Germany ever becomes viable again.

## 5. Honest framing

Portugal (4 stores) and France (2 stores: Auchan, Lidl) remain the project's
only live country coverage. Germany contributes nothing right now — this
should be reflected accurately in any UI/docs copy (no "3 countries" claim)
until a real German data source is found.
