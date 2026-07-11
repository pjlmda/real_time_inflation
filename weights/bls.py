"""Fetch HICP-equivalent item weights for the US from BLS's public CPI API
and sync them into `category_weights` (migration 0007) — the US analogue
of `weights/eurostat.py`.

docs/us-expansion-plan.md §3.1/§4.1 has the full research trail. Summary of
what makes this different from the Eurostat fetcher:

  - There's no single dissemination-API dataset covering all COICOP-mapped
    items the way `prc_hicp_inw` does for Eurostat members. BLS does publish
    an official COICOP/HICP crosswalk (R-COICOP, R-HICP research series),
    but the finished, already-bridged output only exists as `.xlsx` files
    on `bls.gov`/`download.bls.gov`, both confirmed Akamai-blocked with an
    explicit stated anti-automation policy (2026-07-11). What *is* open,
    confirmed live and free with no registration: `api.bls.gov`'s public
    JSON time-series endpoint, which exposes each CPI item's own expenditure
    weight ("Relative Importance") as request-time "aspect metadata" when
    `"aspects": true` is set on the request — a completely different,
    unauthenticated channel from the blocked file downloads.
  - So instead of one bulk fetch translated by a compact-code parser (the
    Eurostat `to_dotted_ecoicop()` approach), this fetches BLS's own native
    item-level series (one POST, up to 50 series per request) and maps each
    one to an ECOICOP code via a hand-built table below — the real, bounded
    "BLS-item-to-COICOP mapping" work flagged as the remaining weights task.
  - Every code in `BLS_ITEM_TO_ECOICOP` was checked live against
    `api.bls.gov` during this module's development (real, current data
    returned; plausible relative-importance magnitude; correct parent/child
    nesting, e.g. Dairy's RI ≥ Milk's + Cheese's). Two codes (`SEFW` for
    wine, `SEGB` for personal care) are sourced from search-engine summaries
    cross-referenced against FRED series titles rather than independently
    live-verified against `api.bls.gov` directly — the daily unauthenticated
    request quota was hit mid-verification. Flagged here rather than left
    silently unstated; worth a follow-up live check before fully trusting
    those two specifically.
  - BLS's own item taxonomy doesn't split rice from pasta the way ECOICOP
    does — both fall under the single item `SEFA03` ("Cereals and bakery
    products: Rice, pasta, cornmeal"). Both `01.1.1.1` (rice) and `01.1.1.6`
    (pasta) map to the same BLS weight below as a disclosed simplification,
    the same kind of granularity gap already documented for other countries
    in `seed/README.md` (e.g. Portugal's potato-folded-into-vegetables).
  - No BLS item code was found for yoghurt specifically — it isn't broken
    out from the broader Dairy aggregate at the level BLS publishes. Left
    unmapped rather than guessed; `01.1.4.4` simply won't get a US weight
    until this is resolved, the same "real gap, not worked around" pattern
    used elsewhere in this project.
  - Olive oil (`01.1.5.3`) and wine (`02.1.2.1`) map to BLS's broader "Fats
    and oils" (`SEFS`) and "Alcoholic beverages at home" (`SEFW`) items
    respectively, since BLS doesn't publish an olive-oil-only or
    wine-only series at this level either — the same kind of
    broader-category substitution, disclosed rather than hidden.
  - BLS's "Relative Importance" is a plain percentage of all-items
    (0-100 scale); Eurostat's `hicp_weight` values already in
    `category_weights` are per-mille (‰, 0-1000 scale — e.g. Portugal's
    bread weight is stored as `17.7`, meaning 1.77% of the basket). Values
    fetched here are multiplied by 10 to match that existing convention
    before being stored, so the column means the same thing across every
    country's rows, not just internally consistent within the US's own.
"""
from __future__ import annotations

import os

import httpx

# WeightRecord/upsert_weights are already country-agnostic (upsert_weights
# takes `country` as a plain param) - reused here rather than duplicated.
from weights.eurostat import WeightRecord, upsert_weights

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SOURCE_DATASET = "bls_cpi_relative_importance"

# BLS CPI item code -> ECOICOP v2 dotted code. See module docstring for
# provenance/verification notes per entry; only covers the
# "supermarket-buyable" subset this project tracks (plan §5).
BLS_ITEM_TO_ECOICOP: dict[str, str] = {
    "SEFA03": "01.1.1.1",  # Rice, pasta, cornmeal (also used for 01.1.1.6, see below)
    "SEFB01": "01.1.1.3",  # Bread
    "SEFC": "01.1.2.1",  # Beef and veal
    "SEFD": "01.1.2.2",  # Pork
    "SEFF": "01.1.2.4",  # Poultry
    "SEFJ01": "01.1.4.1",  # Milk
    "SEFJ02": "01.1.4.5",  # Cheese and related products
    "SEFH": "01.1.4.7",  # Eggs
    "SEFS": "01.1.5.3",  # Fats and oils (olive oil not broken out separately)
    "SEFK": "01.1.6.1",  # Fresh fruits
    "SEFL": "01.1.7.1",  # Fresh vegetables
    "SEFW": "02.1.2.1",  # Alcoholic beverages at home (wine not broken out separately) - not independently live-verified, see module docstring
    "SEGB": "12.1.3.2",  # Personal care products - not independently live-verified, see module docstring
}
# Rice and pasta share the same BLS item (SEFA03) - a disclosed granularity
# gap, not an oversight. Applied as an extra mapping entry below rather than
# folded into the dict literal above, to keep that dict a clean 1:1 view of
# what BLS actually publishes.
BLS_ITEM_TO_ECOICOP_EXTRA_TARGETS: dict[str, list[str]] = {
    "SEFA03": ["01.1.1.1", "01.1.1.6"],
}

PERCENT_TO_PERMILLE = 10  # BLS's Relative Importance (0-100 scale) -> this project's per-mille convention (0-1000, matching Eurostat's hicp_weight)


class BlsRequestFailed(Exception):
    """The BLS API responded but declined to process the request (e.g. the
    daily unauthenticated-quota threshold, confirmed live to be a real,
    fairly easy limit to hit during heavy research use). Raised explicitly
    rather than letting `parse_response` silently treat the missing
    `Results` key the same as "no data for these series" — a rate-limited
    run must be visibly a failure, not a silent zero-record "success"."""


def fetch_weights(*, timeout: float = 30.0) -> list[WeightRecord]:
    """One batched POST for every mapped BLS item (well under the API's
    50-series-per-request limit), `aspects: true` to get each series'
    current Relative Importance alongside its index value."""
    series_ids = list(BLS_ITEM_TO_ECOICOP.keys())
    resp = httpx.post(
        BLS_API_URL,
        json={"seriesid": series_ids, "aspects": True},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise BlsRequestFailed(f"BLS API declined the request: {payload.get('message') or payload.get('status')}")
    return parse_response(payload)


def parse_response(raw: dict) -> list[WeightRecord]:
    """Pure function: BLS API JSON payload -> WeightRecords, one per mapped
    ECOICOP code (more than one output record for SEFA03, since it maps to
    both rice and pasta). Series with no data (e.g. a bad/rate-limited
    request, or a code that turns out not to exist) are skipped, not
    treated as fatal - a partial weights sync is more useful than none."""
    records: list[WeightRecord] = []
    for series in raw.get("Results", {}).get("series", []):
        series_id = series.get("seriesID", "")
        # CUUR0000<item_code> -> strip the 8-char fixed prefix ('CU' survey
        # + 'UR' not-seasonally-adjusted/periodicity + '0000' US city average).
        item_code = series_id[8:] if len(series_id) > 8 else series_id

        data_points = series.get("data", [])
        if not data_points:
            continue
        latest = data_points[0]  # BLS returns most-recent-first
        ri_raw = next(
            (a["value"] for a in latest.get("aspects", []) if a.get("name") == "Relative Importance"),
            None,
        )
        if ri_raw is None:
            continue
        weight = float(ri_raw) * PERCENT_TO_PERMILLE
        weight_year = int(latest["year"])

        targets = BLS_ITEM_TO_ECOICOP_EXTRA_TARGETS.get(item_code)
        if targets is None:
            ecoicop_code = BLS_ITEM_TO_ECOICOP.get(item_code)
            targets = [ecoicop_code] if ecoicop_code else []
        for ecoicop_code in targets:
            records.append(WeightRecord(ecoicop2_code=ecoicop_code, weight_year=weight_year, weight=weight))
    return records


def main() -> None:
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    records = fetch_weights()
    upsert_weights(records, client, country="US", source_dataset=SOURCE_DATASET)
    print(f"Synced {len(records)} weight records for US (BLS CPI relative importance).")


if __name__ == "__main__":
    main()
