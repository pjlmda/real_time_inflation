"""Category-average (dynamic) inflation metrics compute (spec §1, §4.6) — the
robustness/self-healing counterpart to the fixed-basket index in
metrics/compute.py.

Where the fixed-basket index tracks specific curated products, this one
tracks whatever a whole category-listing page shows on a given day, via
`category_observations`'s per (store, category, day) median_price_per_unit.
There's no separate promo/regular price captured there (category crawlers
only extract a single price-per-unit per tile) — so this only ever emits
price_basis='effective'; the median blends together whatever mix of
promo'd/non-promo'd products happened to be on that page that day, and
labeling that 'headline' would overstate what's actually being measured.

Methodology reuses metrics.formulas.weighted_overall_index for every
combination step here, rather than the fixed-basket's Jevons class
aggregation — category_observations rows are already class-level
aggregates (a whole category's median), not per-product elementary prices,
so there's no lower level left to take a Jevons geometric mean across:
  - Per (store, category): relative = median_price_per_unit_t / _0, where
    day 0 is that pair's own first-ever observation (same gap-handling
    philosophy as the fixed-basket — a category added later still gets a
    valid series from its own start, rather than a missing/undefined one).
  - dimension='category' (cross-store): weighted arithmetic mean of every
    contributing store's relative for that class, weighted by n_products
    (that store's sample size that day) — a cross-retailer robustness
    check, not a HICP-weighted figure.
  - dimension='overall'/'store': weighted arithmetic mean across classes
    using hicp_weight, same combination step the fixed-basket uses.
  - inflation_rate: same lookback-period pattern as the fixed-basket,
    reusing metrics.formulas.inflation_rate.

Coverage here is a single global figure per as_of_date — the fraction of
every (store, category) pair ever observed that has a fresh observation
today — applied uniformly to every row this run writes. This is a
simplification versus the fixed-basket's per-scope coverage, adopted to
keep a first cut of this index tractable; a per-row denominator (e.g. per
category, or per store) would be a natural next refinement.

Scheduled as part of `metrics/compute.py`'s single daily compute step
(same run, same alert) rather than a separate workflow — manual run:
`python -m metrics.category_compute`
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, timedelta

from metrics.compute import fetch_category_weights, fetch_lookback_indices, fetch_recent_daily_map
from metrics.formulas import inflation_rate, moving_average, weighted_overall_index

PERIOD_LOOKBACK_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}


def fetch_category_observations(client, store_ids: list[int]) -> list[dict]:
    """Scoped to an explicit store_id list (always one country's stores) —
    same reasoning as metrics/compute.py:fetch_basket_rows: COICOP codes are
    shared across countries, so an unscoped fetch would blend two
    countries' observations into the same category_id's aggregation."""
    if not store_ids:
        return []
    resp = (
        client.table("category_observations")
        .select(
            "store_id, category_id, scrape_date, n_products, median_price_per_unit, "
            "stores(slug), categories(ecoicop2_code)"
        )
        .in_("store_id", store_ids)
        .execute()
    )
    return resp.data


def group_by_pair(rows: list[dict]) -> dict[tuple[int, int], list[dict]]:
    grouped: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["store_id"], row["category_id"])].append(row)
    return grouped


def relative_for_pair(pair_rows: list[dict], as_of_date: str) -> tuple[float, int] | None:
    """Pure: one (store, category) pair's own history -> (relative, n_products
    for as_of_date), or None if there's no observation for as_of_date or the
    base (that pair's own first-ever observation) is non-positive/missing."""
    ordered = sorted(pair_rows, key=lambda r: r["scrape_date"])
    base = ordered[0]["median_price_per_unit"]
    if not base or base <= 0:
        return None
    today_row = next((r for r in ordered if r["scrape_date"] == as_of_date), None)
    if today_row is None or today_row["median_price_per_unit"] is None:
        return None
    relative = float(today_row["median_price_per_unit"]) / float(base)
    return relative, int(today_row["n_products"] or 0)


def build_index_rows(
    as_of_date: str,
    dimension: str,
    dimension_value: str,
    index_value: float,
    n_products: int,
    coverage: float,
    country: str,
    lookback: dict[tuple[str, str, str, str], float],
    recent_daily: dict[tuple[str, str, str], list[float]],
) -> list[dict]:
    """Pure: builds this scope's 4 period rows from precomputed
    lookback/recent-daily maps (see metrics.compute.fetch_lookback_indices /
    fetch_recent_daily_map, reused here with index_family='category_avg') —
    no DB access here. The caller batches every scope's rows into one
    upsert, instead of the one-query-per-(scope, period) pattern this used
    to run (same fix as metrics/compute.py's fixed-basket family)."""
    rows = []
    for period in PERIOD_LOOKBACK_DAYS:
        row = {
            "as_of_date": as_of_date,
            "index_family": "category_avg",
            "period": period,
            "dimension": dimension,
            "dimension_value": dimension_value,
            "price_basis": "effective",
            "index_value": round(index_value, 4),
            "index_value_ma7": None,
            "inflation_rate": None,
            "n_products": n_products,
            "coverage": round(coverage, 4),
            "country": country,
        }
        if period == "daily":
            history = recent_daily.get((dimension, dimension_value, "effective"), [])
            row["index_value_ma7"] = round(moving_average(history + [index_value]), 4)
        past_index = lookback.get((period, dimension, dimension_value, "effective"))
        if past_index is not None:
            row["inflation_rate"] = round(inflation_rate(index_value, past_index), 4)
        rows.append(row)
    return rows


def compute_category_avg_metrics_for_date(client, as_of_date: str) -> list[dict]:
    stores = client.table("stores").select("id, slug, country").execute().data
    stores_by_country: dict[str, list[dict]] = {}
    for store in stores:
        stores_by_country.setdefault(store["country"], []).append(store)

    written: list[dict] = []
    for country, country_stores in stores_by_country.items():
        rows = fetch_category_observations(client, [s["id"] for s in country_stores])
        if not rows:
            continue

        hicp_weight = fetch_category_weights(client, country)
        lookback = fetch_lookback_indices(client, as_of_date, country, index_family="category_avg")
        recent_daily = fetch_recent_daily_map(client, as_of_date, country, index_family="category_avg")
        country_rows: list[dict] = []
        grouped = group_by_pair(rows)
        n_total_pairs = len(grouped)
        n_covered_pairs = 0

        # ecoicop2_code -> [(index_value, n_products)] for every store reporting it today.
        per_category: dict[str, list[tuple[float, float]]] = defaultdict(list)
        # store_slug -> {ecoicop2_code: index_value} — that store's own categories only.
        per_store: dict[str, dict[str, float]] = defaultdict(dict)

        for (_store_id, _category_id), pair_rows in grouped.items():
            sample = pair_rows[0]
            code = sample["categories"]["ecoicop2_code"]
            slug = sample["stores"]["slug"]

            result = relative_for_pair(pair_rows, as_of_date)
            if result is None:
                continue
            n_covered_pairs += 1
            relative, n_products = result
            index_value = relative * 100
            per_category[code].append((index_value, float(n_products or 1)))
            per_store[slug][code] = index_value

        coverage = (n_covered_pairs / n_total_pairs) if n_total_pairs else 0.0

        # --- dimension='category' (cross-store blend within this country) ---
        class_indices: dict[str, float] = {}
        for code, pairs in per_category.items():
            index_value = weighted_overall_index(pairs)
            class_indices[code] = index_value
            n_products_total = int(sum(w for _, w in pairs))
            country_rows += build_index_rows(
                as_of_date, "category", code, index_value, n_products_total, coverage, country, lookback, recent_daily
            )

        # --- dimension='overall' ---
        overall_pairs = [
            (idx, hicp_weight[code]) for code, idx in class_indices.items() if hicp_weight.get(code, 0) > 0
        ]
        if overall_pairs:
            overall_index = weighted_overall_index(overall_pairs)
            n_products_total = sum(int(sum(w for _, w in per_category[code])) for code in class_indices)
            country_rows += build_index_rows(
                as_of_date, "overall", "ALL", overall_index, n_products_total, coverage, country, lookback, recent_daily
            )

        # --- dimension='store' (that store's own categories only, not cross-store blended) ---
        for slug, code_indices in per_store.items():
            store_pairs = [
                (idx, hicp_weight[code]) for code, idx in code_indices.items() if hicp_weight.get(code, 0) > 0
            ]
            if store_pairs:
                store_index = weighted_overall_index(store_pairs)
                country_rows += build_index_rows(
                    as_of_date, "store", slug, store_index, len(code_indices), coverage, country, lookback, recent_daily
                )

        if country_rows:
            client.table("inflation_metrics").upsert(
                country_rows,
                on_conflict="as_of_date,index_family,period,dimension,dimension_value,price_basis,country",
            ).execute()
        written += country_rows

    return written


def main() -> None:
    from dotenv import load_dotenv
    from supabase import create_client

    from scraper.db import scrape_date_for_timezone

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    as_of_date = scrape_date_for_timezone()
    rows = compute_category_avg_metrics_for_date(client, as_of_date)
    print(f"Wrote {len(rows)} category_avg inflation_metrics rows for {as_of_date}.")


if __name__ == "__main__":
    main()
