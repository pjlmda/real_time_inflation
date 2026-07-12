"""Fixed-basket inflation metrics compute (spec §6, §11 step 7).

Emits, per price_basis (headline=regular_price, effective=price):
  - dimension='overall': one combined index across every active store.
  - dimension='category': one index per ECOICOP class, across every store
    that carries a product in it — the "per ECOICOP category" cut (spec
    §1), a global breakdown rather than a per-store one.
  - dimension='store': one combined index per store (all its categories
    weighted together) — the "per store" cut.

index_value=100 rows land from day 1 (spec: "base 100 at series start").
inflation_rate is only filled in when an inflation_metrics row already
exists at the lookback date, so daily/weekly/monthly/yearly rates appear on
their own once enough history accumulates — no code change needed when that
happens.

Scoped to index_family='fixed_basket' only — category_avg needs
category_observations history to exist first (a natural next increment).

Scheduled via `.github/workflows/compute.yml`, triggered on `scrape.yml`
completion. Manual run: `python -m metrics.compute`
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from datetime import date, timedelta

from metrics.formulas import inflation_rate, jevons_class_index, moving_average, weighted_overall_index

PRICE_BASES = [("headline", "regular_price"), ("effective", "price")]
PERIOD_LOOKBACK_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}


def fetch_basket_rows(client, store_ids: list[int]) -> list[dict]:
    """Scoped to an explicit store_id list — always either every store in one
    country (for the 'overall'/'category' dimensions) or a single store (for
    the 'store' dimension). Never unscoped: COICOP codes are the same
    international taxonomy across countries, so mixing two countries'
    listings into one aggregation would silently blend their prices
    together (spec: see docs/france-expansion-plan.md §3.1)."""
    if not store_ids:
        return []
    return (
        client.table("product_listings")
        .select(
            "id, store_id, "
            "products(category_id, within_cat_weight, "
            "categories(ecoicop2_code))"
        )
        .eq("is_active", True)
        .in_("store_id", store_ids)
        .execute()
        .data
    )


def fetch_category_weights(client, country: str) -> dict[str, float]:
    """ecoicop2_code -> hicp_weight for one country (category_weights,
    migration 0007) — weights are country-specific even though the COICOP
    code/name taxonomy in `categories` itself is shared."""
    resp = (
        client.table("category_weights")
        .select("ecoicop2_code, hicp_weight")
        .eq("country", country)
        .execute()
    )
    return {
        row["ecoicop2_code"]: float(row["hicp_weight"])
        for row in resp.data
        if row["hicp_weight"] is not None
    }


def fetch_snapshots_by_listing(client, listing_ids: list[int]) -> dict[int, list[dict]]:
    if not listing_ids:
        return {}
    resp = (
        client.table("price_snapshots")
        .select("listing_id, scrape_date, price, regular_price")
        .in_("listing_id", listing_ids)
        .execute()
    )
    by_listing: dict[int, list[dict]] = {}
    for row in resp.data:
        by_listing.setdefault(row["listing_id"], []).append(row)
    return by_listing


def base_and_current_price(
    snapshots: list[dict], as_of_date: str, price_field: str
) -> tuple[float, float] | None:
    """Pure: a listing's own first-ever scrape_date is day 0 (spec §6 gaps
    handling — a product added later still gets a valid relative from its
    own start). None if there's no snapshot for as_of_date (missing today —
    excluded from n_products/coverage rather than erroring)."""
    if not snapshots:
        return None
    ordered = sorted(snapshots, key=lambda r: r["scrape_date"])
    base_row = ordered[0]
    today_row = next((r for r in ordered if r["scrape_date"] == as_of_date), None)
    if today_row is None:
        return None
    return float(base_row[price_field]), float(today_row[price_field])


def class_relatives(
    basket_rows: list[dict],
    snapshots_by_listing: dict[int, list[dict]],
    as_of_date: str,
    price_field: str,
) -> tuple[dict[str, list[tuple[float, float]]], int]:
    """Groups listings by ECOICOP class. Returns (relatives-and-weights per
    ecoicop2_code, n_covered). HICP weights are looked up separately, once
    per country, via fetch_category_weights — they're not a property of the
    basket row itself (categories is a shared, country-agnostic taxonomy;
    weights are country-specific, see migration 0007)."""
    by_category: dict[str, list[tuple[float, float]]] = {}
    n_covered = 0
    for row in basket_rows:
        product = row["products"]
        category = product["categories"]
        result = base_and_current_price(
            snapshots_by_listing.get(row["id"], []), as_of_date, price_field
        )
        if result is None:
            continue
        base_price, current_price = result
        if base_price <= 0:
            continue
        relative = current_price / base_price
        weight = float(product["within_cat_weight"]) if product["within_cat_weight"] else 1.0
        code = category["ecoicop2_code"]
        by_category.setdefault(code, []).append((relative, weight))
        n_covered += 1
    return by_category, n_covered


def fetch_lookback_indices(
    client, as_of_date: str, country: str, index_family: str = "fixed_basket"
) -> dict[tuple[str, str, str, str], float]:
    """One batched read replacing what used to be one query per
    (scope, period) — up to hundreds of round trips per compute run. Each
    period's lookback date (as_of_date - N days) is the same across every
    scope, so a single `as_of_date IN (...)` query covers every
    period/dimension/dimension_value/price_basis combination for this
    country+family in one round trip. Safe to precompute before any writes
    this run makes: every target_date is strictly before as_of_date, so this
    can never see a row this same run is about to write.
    Keyed by (period, dimension, dimension_value, price_basis)."""
    target_dates = {
        period: (date.fromisoformat(as_of_date) - timedelta(days=days)).isoformat()
        for period, days in PERIOD_LOOKBACK_DAYS.items()
    }
    date_to_period = {v: k for k, v in target_dates.items()}
    resp = (
        client.table("inflation_metrics")
        .select("as_of_date, dimension, dimension_value, price_basis, index_value")
        .eq("index_family", index_family)
        .eq("country", country)
        .in_("as_of_date", list(date_to_period))
        .execute()
    )
    lookback: dict[tuple[str, str, str, str], float] = {}
    for row in resp.data:
        period = date_to_period.get(row["as_of_date"])
        if period is None:
            continue
        key = (period, row["dimension"], row["dimension_value"], row["price_basis"])
        lookback[key] = float(row["index_value"])
    return lookback


def fetch_recent_daily_map(
    client, as_of_date: str, country: str, index_family: str = "fixed_basket", days: int = 6
) -> dict[tuple[str, str, str], list[float]]:
    """One batched read replacing what used to be one query per scope — the
    prior `days` days of every scope's raw daily index_value, fetched once
    per country+family instead of once per
    (dimension, dimension_value, price_basis) (spec §6: "raw daily is noisy
    from rounding/promos", the input to the 7-day moving average).
    Keyed by (dimension, dimension_value, price_basis)."""
    start_date = (date.fromisoformat(as_of_date) - timedelta(days=days)).isoformat()
    end_date = (date.fromisoformat(as_of_date) - timedelta(days=1)).isoformat()
    resp = (
        client.table("inflation_metrics")
        .select("dimension, dimension_value, price_basis, index_value")
        .eq("index_family", index_family)
        .eq("period", "daily")
        .eq("country", country)
        .gte("as_of_date", start_date)
        .lte("as_of_date", end_date)
        .order("as_of_date")
        .execute()
    )
    recent: dict[tuple[str, str, str], list[float]] = {}
    for row in resp.data:
        key = (row["dimension"], row["dimension_value"], row["price_basis"])
        recent.setdefault(key, []).append(float(row["index_value"]))
    return recent


def build_index_rows(
    as_of_date: str,
    dimension: str,
    dimension_value: str,
    price_basis: str,
    index_value: float,
    n_products: int,
    coverage: float,
    country: str,
    lookback: dict[tuple[str, str, str, str], float],
    recent_daily: dict[tuple[str, str, str], list[float]],
) -> list[dict]:
    """Pure: builds this scope's 4 period rows (daily/weekly/monthly/yearly)
    from precomputed lookback/recent-daily maps instead of querying per
    period (see fetch_lookback_indices/fetch_recent_daily_map) — no DB
    access here. The caller batches every scope's rows into one upsert."""
    rows = []
    for period in PERIOD_LOOKBACK_DAYS:
        row = {
            "as_of_date": as_of_date,
            "index_family": "fixed_basket",
            "period": period,
            "dimension": dimension,
            "dimension_value": dimension_value,
            "price_basis": price_basis,
            "index_value": round(index_value, 4),
            "index_value_ma7": None,
            "inflation_rate": None,
            "n_products": n_products,
            "coverage": round(coverage, 4),
            "country": country,
        }
        if period == "daily":
            history = recent_daily.get((dimension, dimension_value, price_basis), [])
            row["index_value_ma7"] = round(moving_average(history + [index_value]), 4)
        past_index = lookback.get((period, dimension, dimension_value, price_basis))
        if past_index is not None:
            row["inflation_rate"] = round(inflation_rate(index_value, past_index), 4)
        rows.append(row)
    return rows


def _compute_scope(
    as_of_date: str, basket_rows: list[dict], snapshots_by_listing: dict[int, list[dict]]
) -> Iterator[tuple[str, dict[str, list[tuple[float, float]]], int, float]]:
    """Computes per-category relatives for one scope's basket_rows, given an
    already-fetched snapshots map (see compute_metrics_for_date — snapshots
    are fetched once per country, covering every store's listings, and
    reused for every per-store scope instead of being re-fetched per store
    for what's always a subset of the same listings). Returns the inputs
    needed for both the 'category' rows and the weighted combination (caller
    decides whether to label the combination 'overall' or 'store', and
    supplies the country-scoped hicp_weight lookup)."""
    listing_ids = [r["id"] for r in basket_rows]
    for price_basis, price_field in PRICE_BASES:
        by_category, n_covered = class_relatives(basket_rows, snapshots_by_listing, as_of_date, price_field)
        coverage = n_covered / len(listing_ids) if listing_ids else 0.0
        yield price_basis, by_category, n_covered, coverage


def compute_metrics_for_date(client, as_of_date: str) -> list[dict]:
    written: list[dict] = []
    stores = client.table("stores").select("id, slug, country").execute().data
    stores_by_country: dict[str, list[dict]] = {}
    for store in stores:
        stores_by_country.setdefault(store["country"], []).append(store)

    for country, country_stores in stores_by_country.items():
        hicp_weight = fetch_category_weights(client, country)
        lookback = fetch_lookback_indices(client, as_of_date, country)
        recent_daily = fetch_recent_daily_map(client, as_of_date, country)
        country_rows: list[dict] = []

        # --- overall (all stores in this country) + per-category (across this country's stores) ---
        overall_rows = fetch_basket_rows(client, [s["id"] for s in country_stores])
        snapshots_by_listing = fetch_snapshots_by_listing(client, [r["id"] for r in overall_rows])
        overall_rows_by_store: dict[int, list[dict]] = {}
        for row in overall_rows:
            overall_rows_by_store.setdefault(row["store_id"], []).append(row)

        for price_basis, by_category, n_covered, coverage in _compute_scope(
            as_of_date, overall_rows, snapshots_by_listing
        ):
            class_indices: dict[str, float] = {}
            for code, relatives_and_weights in by_category.items():
                index = jevons_class_index(relatives_and_weights)
                class_indices[code] = index
                country_rows += build_index_rows(
                    as_of_date, "category", code, price_basis, index,
                    len(relatives_and_weights), coverage, country, lookback, recent_daily,
                )

            overall_pairs = [
                (idx, hicp_weight[code]) for code, idx in class_indices.items() if hicp_weight.get(code, 0) > 0
            ]
            if overall_pairs:
                overall_index = weighted_overall_index(overall_pairs)
                country_rows += build_index_rows(
                    as_of_date, "overall", "ALL", price_basis, overall_index,
                    n_covered, coverage, country, lookback, recent_daily,
                )

        # --- per-store (combined across that store's own categories) ---
        for store in country_stores:
            store_rows = overall_rows_by_store.get(store["id"], [])
            if not store_rows:
                continue
            for price_basis, by_category, n_covered, coverage in _compute_scope(
                as_of_date, store_rows, snapshots_by_listing
            ):
                class_indices = {code: jevons_class_index(rw) for code, rw in by_category.items()}
                store_pairs = [
                    (idx, hicp_weight[code]) for code, idx in class_indices.items() if hicp_weight.get(code, 0) > 0
                ]
                if store_pairs:
                    store_index = weighted_overall_index(store_pairs)
                    country_rows += build_index_rows(
                        as_of_date, "store", store["slug"], price_basis, store_index,
                        n_covered, coverage, country, lookback, recent_daily,
                    )

        if country_rows:
            client.table("inflation_metrics").upsert(
                country_rows,
                on_conflict="as_of_date,index_family,period,dimension,dimension_value,price_basis,country",
            ).execute()
        written += country_rows

    return written


def main() -> None:
    import asyncio

    from dotenv import load_dotenv
    from supabase import create_client

    from alerting.base import Notifier
    from alerting.console import ConsoleNotifier
    from alerting.telegram import TelegramNotifier
    from metrics.category_compute import compute_category_avg_metrics_for_date
    from scraper.db import scrape_date_for_timezone

    load_dotenv()

    notifier: Notifier
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        notifier = TelegramNotifier(token=token, chat_id=chat_id)
    else:
        print(
            "WARNING: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID not set — alerts will only "
            "print to the console, not reach Telegram.",
            file=sys.stderr,
        )
        notifier = ConsoleNotifier()

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    # One as_of_date for the whole run, in the original/primary country's
    # timezone — every country's compute_metrics_for_date call below shares
    # it. Right at a country's own local midnight this can be off by a day
    # for that country specifically (same accepted-tradeoff pattern already
    # used for the scrape.yml cron's UTC/DST drift); a fully correct
    # per-country "today" would mean running this job separately per
    # country, not attempted yet (docs/france-expansion-plan.md §3.3).
    as_of_date = scrape_date_for_timezone()

    # Spec §8: "compute job error / missing daily metrics" is an alertable
    # incident, same tier as a failed scrape — a stale index is silent
    # otherwise, since nothing else re-checks that today's row landed. Both
    # index families run in this one job/alert (spec §0: "computed in
    # parallel") rather than a separate workflow for category_avg.
    try:
        rows = compute_metrics_for_date(client, as_of_date)
        category_rows = compute_category_avg_metrics_for_date(client, as_of_date)
    except Exception as exc:
        asyncio.run(notifier.send(f"*Compute job failed* for {as_of_date}:\n{exc}"))
        raise

    print(
        f"Wrote {len(rows)} fixed-basket + {len(category_rows)} category-avg "
        f"inflation_metrics rows for {as_of_date}."
    )
    if not rows and not category_rows:
        asyncio.run(
            notifier.send(
                f"*Compute job produced no metrics* for {as_of_date} — "
                "check basket coverage and today's price_snapshots/category_observations."
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
