"""EIA (U.S. Energy Information Administration) weekly retail gasoline/
diesel price fetcher — the US analogue of fuel/dgeg.py. Uses EIA's Open
Data API v2 (api.eia.gov/v2/petroleum/pri/gnd/), a free, official, JSON
endpoint published on EIA's own weekly cadence (Monday-collected data) —
by explicit decision this project tracks that native weekly cadence
rather than reaching for a same-cadence-as-DGEG daily source: AAA
(gasprices.aaa.com) is technically scrapable (permissive robots.txt,
price rendered in plain server HTML) but its data is OPIS-sourced (a
commercial vendor) with no explicit free-reuse statement found on the
page, unlike DGEG's explicit non-commercial-use grant — a materially
weaker legal footing this project chose not to build against.

Structured like weights/bls.py (plain sync httpx, pure parse function,
explicit *RequestFailed exception), not like fuel/dgeg.py (Playwright
browser automation) — EIA has a real REST API, so no browser is needed.

Unlike weights/bls.py's optional BLS_API_KEY (25 unauthenticated
req/day, 500 registered), EIA's v2 API requires a registered key for
EVERY request — there is no anonymous tier. Register free at
https://www.eia.gov/opendata/register.php.

PADD region duoarea codes below (R10/R20/R30/R40/R50) and product codes
(EPMR/EPD2D) are sourced from EIA's legacy series-ID naming convention
(e.g. EMM_EPMR_PTE_R10_DPG) — a STARTING HYPOTHESIS, NOT yet independently
live-verified as of this module's authoring (no EIA_API_KEY was available
during development). Before the first production run, confirm these
against EIA's own facet metadata endpoints, which return the
authoritative id/name pairs for every valid value on this route:

    GET https://api.eia.gov/v2/petroleum/pri/gnd/facet/duoarea/?api_key=...
    GET https://api.eia.gov/v2/petroleum/pri/gnd/facet/product/?api_key=...

Update PADD_REGIONS/PRODUCT_CODES from that response's actual ids if they
differ from the guess below, and record the confirmation in
docs/us-expansion-plan.md the way every other source's live verification
in this project is documented. parse_response() is defensive regardless
of whether the guess turns out right: any duoarea code not in
PADD_REGIONS/NATIONAL_DUOAREA is skipped, not guessed at or mislabeled,
so an uncaught wrong guess fails safe (fewer rows), never unsafe
(mislabeled rows).
"""
from __future__ import annotations

import os

import httpx

EIA_API_URL = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
SOURCE = "eia_weekly_retail"

# Our internal fuel_type slug -> EIA's `product` facet code.
PRODUCT_CODES: dict[str, str] = {
    "gasoline_regular": "EPMR",
    "diesel": "EPD2D",
}

NATIONAL_DUOAREA = "NUS"

# EIA `duoarea` facet code -> our `region` column value.
PADD_REGIONS: dict[str, str] = {
    "R10": "PADD1",  # East Coast
    "R20": "PADD2",  # Midwest
    "R30": "PADD3",  # Gulf Coast
    "R40": "PADD4",  # Rocky Mountain
    "R50": "PADD5",  # West Coast
}

# EIA's own `units` field value -> this project's unit-string convention
# (matches DGEG's 'EUR/<abbrev>' shape, e.g. 'EUR/L').
EIA_UNIT_MAP = {"$/GAL": "USD/gal"}


class EiaRequestFailed(Exception):
    """The EIA API call couldn't be trusted as real data — either
    EIA_API_KEY wasn't set (v2 requires one for every request, unlike
    BLS's unauthenticated tier), an HTTP-level error was returned, or the
    API responded 200 with its own error payload (bad key, invalid facet
    value, etc). Raised explicitly, same reasoning as
    weights.bls.BlsRequestFailed: a declined/misconfigured request must
    be visibly a failure, never silently parsed as "zero rows today"."""


def fetch_all_latest_prices(*, timeout: float = 30.0) -> list[dict]:
    """One GET per configured product, covering national + all 5 PADD
    regions via facets[duoarea][] in a single request each. Returns a flat
    list of rows, each self-describing: {fuel_type, region, date, price,
    unit, raw_payload}. Never touches Supabase — safe to call standalone
    to inspect output before any DB write is attempted."""
    api_key = os.environ.get("EIA_API_KEY")
    if not api_key:
        raise EiaRequestFailed(
            "EIA_API_KEY not set — EIA's v2 API requires a registered key "
            "for every request (no anonymous tier, unlike BLS). Register "
            "free at https://www.eia.gov/opendata/register.php"
        )

    rows: list[dict] = []
    for fuel_type, product_code in PRODUCT_CODES.items():
        params = {
            "api_key": api_key,
            "frequency": "weekly",
            "data[0]": "value",
            "facets[product][]": product_code,
            "facets[duoarea][]": [NATIONAL_DUOAREA, *PADD_REGIONS],
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": (len(PADD_REGIONS) + 1) * 2,  # a little slack past 1 row/duoarea
        }
        resp = httpx.get(EIA_API_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise EiaRequestFailed(f"EIA API declined the request: {payload['error']}")
        rows.extend(parse_response(payload, fuel_type))
    return rows


def parse_response(raw: dict, fuel_type: str) -> list[dict]:
    """Pure function: one EIA v2 JSON response (already scoped to one
    product) -> list of row dicts, one per recognized duoarea, keeping
    only each duoarea's most-recent period (EIA returns desc-sorted, but
    this dedupes defensively rather than assuming request-level sort
    held)."""
    records = raw.get("response", {}).get("data", [])
    seen_duoareas: set[str] = set()
    results: list[dict] = []
    for rec in records:
        duoarea = rec.get("duoarea")
        if duoarea == NATIONAL_DUOAREA:
            region = "NATIONAL"
        elif duoarea in PADD_REGIONS:
            region = PADD_REGIONS[duoarea]
        else:
            continue  # unrecognized duoarea - fail safe, don't guess (see module docstring)
        if duoarea in seen_duoareas:
            continue  # already took this duoarea's latest (desc-sorted) row
        seen_duoareas.add(duoarea)

        raw_unit = rec.get("units", "")
        unit = EIA_UNIT_MAP.get(raw_unit, raw_unit)
        results.append(
            {
                "fuel_type": fuel_type,
                "region": region,
                "date": rec["period"],
                "price": float(rec["value"]),
                "unit": unit,
                "raw_payload": rec,
            }
        )
    return results
