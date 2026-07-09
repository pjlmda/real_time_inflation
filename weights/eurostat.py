"""Fetch HICP item weights for Portugal from Eurostat's dissemination API
(dataset `prc_hicp_inw`) and sync them into `categories` / `hicp_weights_cache`.

Weights must never be hardcoded (spec §0 classification note) — this module
is the only source of truth for `categories.hicp_weight`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

EUROSTAT_API_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_inw"
)
SOURCE_DATASET = "prc_hicp_inw"


@dataclass(frozen=True)
class WeightRecord:
    ecoicop2_code: str
    weight_year: int
    weight: float


def fetch_weights(geo: str = "PT", *, timeout: float = 30.0) -> list[WeightRecord]:
    """Pull the full PT weight series from Eurostat and return only the
    latest available year's records (max `time` present in the response)."""
    params = {"geo": geo, "format": "JSON", "lang": "EN"}
    resp = httpx.get(EUROSTAT_API_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return parse_response(resp.json())


def parse_response(raw: dict) -> list[WeightRecord]:
    """Pure function: JSON-stat v2 payload -> latest-year WeightRecords.

    Unit-tested against a saved fixture so tests don't depend on network
    access or Eurostat's uptime.
    """
    dimension = raw["dimension"]
    coicop_index: dict[str, int] = dimension["coicop"]["category"]["index"]
    time_index: dict[str, int] = dimension["time"]["category"]["index"]
    sizes: list[int] = raw["size"]
    # JSON-stat dimension order matches `raw["id"]`; compute strides for the
    # flat `value` map (keyed by stringified flat index in row-major order).
    dim_ids: list[str] = raw["id"]
    strides = [1] * len(dim_ids)
    for i in range(len(dim_ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    coicop_dim = dim_ids.index("coicop")
    time_dim = dim_ids.index("time")

    values: dict[str, float] = raw["value"]
    latest_year = max(int(y) for y in time_index)

    records: list[WeightRecord] = []
    for code, coicop_pos in coicop_index.items():
        time_pos = time_index[str(latest_year)]
        flat_index = coicop_pos * strides[coicop_dim] + time_pos * strides[time_dim]
        raw_value = values.get(str(flat_index))
        if raw_value is None:
            continue
        records.append(
            WeightRecord(
                ecoicop2_code=to_dotted_ecoicop(code),
                weight_year=latest_year,
                weight=float(raw_value),
            )
        )
    return records


def to_dotted_ecoicop(eurostat_code: str) -> str:
    """Eurostat's `prc_hicp_inw` API returns coicop codes in its own compact
    form (`CP01113`, `CP0114`, aggregates like `TOT_X_TBC`) rather than
    dotted ECOICOP v2 notation (`01.1.1.3`). Convert: first 2 digits after
    the optional `CP` prefix are the division, every digit after that starts
    a new dot-separated level. Non-numeric aggregate codes (TOT_X_*, CP00)
    pass through mostly unchanged and simply won't match any seeded leaf
    category, which is the desired behavior."""
    digits = eurostat_code[2:] if eurostat_code.startswith("CP") else eurostat_code
    if len(digits) < 2 or not digits.isdigit():
        return eurostat_code
    return ".".join([digits[:2], *digits[2:]])


def upsert_weights(records: list[WeightRecord], supabase_client, country: str) -> None:
    """Append every fetched record to `hicp_weights_cache` (audit log, safe
    to re-run), then upsert `category_weights` (migration 0007 — weights are
    country-specific, unlike `categories` itself which stays the shared,
    country-agnostic COICOP taxonomy) for the ECOICOP codes already seeded."""
    if not records:
        return

    cache_rows = [
        {
            "ecoicop2_code": r.ecoicop2_code,
            "weight_year": r.weight_year,
            "weight": r.weight,
            "source_dataset": SOURCE_DATASET,
            "country": country,
        }
        for r in records
    ]
    supabase_client.table("hicp_weights_cache").insert(cache_rows).execute()

    seeded = {
        row["ecoicop2_code"]
        for row in supabase_client.table("categories").select("ecoicop2_code").execute().data
    }
    for r in records:
        if r.ecoicop2_code not in seeded:
            continue
        supabase_client.table("category_weights").upsert(
            {
                "ecoicop2_code": r.ecoicop2_code,
                "country": country,
                "hicp_weight": r.weight,
                "weight_year": r.weight_year,
            },
            on_conflict="ecoicop2_code,country",
        ).execute()


def main() -> None:
    import argparse

    from dotenv import load_dotenv
    from supabase import create_client

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--geo",
        default="PT",
        help="Eurostat geo code / country to fetch+store weights for, e.g. PT or FR",
    )
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    records = fetch_weights(geo=args.geo)
    upsert_weights(records, client, country=args.geo)
    print(f"Synced {len(records)} weight records for {args.geo} (latest year found in response).")


if __name__ == "__main__":
    main()
