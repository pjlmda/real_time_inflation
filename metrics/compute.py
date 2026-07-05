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

from metrics.formulas import inflation_rate, jevons_class_index, weighted_overall_index

PRICE_BASES = [("headline", "regular_price"), ("effective", "price")]
PERIOD_LOOKBACK_DAYS = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}


def fetch_basket_rows(client, store_id: int | None = None) -> list[dict]:
    query = (
        client.table("product_listings")
        .select(
            "id, store_id, "
            "products(category_id, within_cat_weight, "
            "categories(ecoicop2_code, hicp_weight))"
        )
        .eq("is_active", True)
    )
    if store_id is not None:
        query = query.eq("store_id", store_id)
    return query.execute().data


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
) -> tuple[dict[str, list[tuple[float, float]]], dict[str, float], int]:
    """Groups listings by ECOICOP class. Returns (relatives-and-weights per
    ecoicop2_code, hicp_weight per ecoicop2_code, n_covered)."""
    by_category: dict[str, list[tuple[float, float]]] = {}
    hicp_weight: dict[str, float] = {}
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
        hicp_weight[code] = float(category["hicp_weight"]) if category["hicp_weight"] else 0.0
        n_covered += 1
    return by_category, hicp_weight, n_covered


def _existing_index(
    client, as_of_date: str, period: str, dimension: str, dimension_value: str, price_basis: str
) -> float | None:
    target_date = (date.fromisoformat(as_of_date) - timedelta(days=PERIOD_LOOKBACK_DAYS[period])).isoformat()
    resp = (
        client.table("inflation_metrics")
        .select("index_value")
        .eq("as_of_date", target_date)
        .eq("index_family", "fixed_basket")
        .eq("period", period)
        .eq("dimension", dimension)
        .eq("dimension_value", dimension_value)
        .eq("price_basis", price_basis)
        .limit(1)
        .execute()
    )
    return float(resp.data[0]["index_value"]) if resp.data else None


def _write_index_and_rates(
    client,
    as_of_date: str,
    dimension: str,
    dimension_value: str,
    price_basis: str,
    index_value: float,
    n_products: int,
    coverage: float,
) -> list[dict]:
    written = []
    for period in PERIOD_LOOKBACK_DAYS:
        row = {
            "as_of_date": as_of_date,
            "index_family": "fixed_basket",
            "period": period,
            "dimension": dimension,
            "dimension_value": dimension_value,
            "price_basis": price_basis,
            "index_value": round(index_value, 4),
            "inflation_rate": None,
            "n_products": n_products,
            "coverage": round(coverage, 4),
        }
        past_index = _existing_index(client, as_of_date, period, dimension, dimension_value, price_basis)
        if past_index is not None:
            row["inflation_rate"] = round(inflation_rate(index_value, past_index), 4)
        client.table("inflation_metrics").upsert(
            row, on_conflict="as_of_date,index_family,period,dimension,dimension_value,price_basis"
        ).execute()
        written.append(row)
    return written


def _compute_scope(
    client, as_of_date: str, basket_rows: list[dict]
) -> Iterator[tuple[str, dict[str, list[tuple[float, float]]], dict[str, float], int, float]]:
    """Computes per-category class indices for one scope's basket_rows, plus
    the weighted combination across those classes. Returns the written
    'category' rows plus the combined row's inputs (caller decides whether
    to label the combination 'overall' or 'store')."""
    written: list[dict] = []
    listing_ids = [r["id"] for r in basket_rows]
    snapshots = fetch_snapshots_by_listing(client, listing_ids)

    for price_basis, price_field in PRICE_BASES:
        by_category, hicp_weight, n_covered = class_relatives(
            basket_rows, snapshots, as_of_date, price_field
        )
        coverage = n_covered / len(listing_ids) if listing_ids else 0.0
        yield price_basis, by_category, hicp_weight, n_covered, coverage


def compute_metrics_for_date(client, as_of_date: str) -> list[dict]:
    written: list[dict] = []
    stores = client.table("stores").select("id, slug").execute().data

    # --- overall (all stores) + per-category (across all stores) ---
    overall_rows = fetch_basket_rows(client, store_id=None)
    for price_basis, by_category, hicp_weight, n_covered, coverage in _compute_scope(
        client, as_of_date, overall_rows
    ):
        class_indices: dict[str, float] = {}
        for code, relatives_and_weights in by_category.items():
            index = jevons_class_index(relatives_and_weights)
            class_indices[code] = index
            written += _write_index_and_rates(
                client, as_of_date, "category", code, price_basis,
                index, len(relatives_and_weights), coverage,
            )

        overall_pairs = [
            (idx, hicp_weight[code]) for code, idx in class_indices.items() if hicp_weight.get(code, 0) > 0
        ]
        if overall_pairs:
            overall_index = weighted_overall_index(overall_pairs)
            written += _write_index_and_rates(
                client, as_of_date, "overall", "ALL", price_basis,
                overall_index, n_covered, coverage,
            )

    # --- per-store (combined across that store's own categories) ---
    for store in stores:
        store_rows = fetch_basket_rows(client, store_id=store["id"])
        if not store_rows:
            continue
        for price_basis, by_category, hicp_weight, n_covered, coverage in _compute_scope(
            client, as_of_date, store_rows
        ):
            class_indices = {code: jevons_class_index(rw) for code, rw in by_category.items()}
            store_pairs = [
                (idx, hicp_weight[code]) for code, idx in class_indices.items() if hicp_weight.get(code, 0) > 0
            ]
            if store_pairs:
                store_index = weighted_overall_index(store_pairs)
                written += _write_index_and_rates(
                    client, as_of_date, "store", store["slug"], price_basis,
                    store_index, n_covered, coverage,
                )

    return written


def main() -> None:
    import asyncio

    from dotenv import load_dotenv
    from supabase import create_client

    from alerting.base import Notifier
    from alerting.console import ConsoleNotifier
    from alerting.telegram import TelegramNotifier
    from scraper.db import lisbon_scrape_date

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
    as_of_date = lisbon_scrape_date()

    # Spec §8: "compute job error / missing daily metrics" is an alertable
    # incident, same tier as a failed scrape — a stale index is silent
    # otherwise, since nothing else re-checks that today's row landed.
    try:
        rows = compute_metrics_for_date(client, as_of_date)
    except Exception as exc:
        asyncio.run(notifier.send(f"*Compute job failed* for {as_of_date}:\n{exc}"))
        raise

    print(f"Wrote {len(rows)} inflation_metrics rows for {as_of_date}.")
    if not rows:
        asyncio.run(
            notifier.send(
                f"*Compute job produced no metrics* for {as_of_date} — "
                "check basket coverage and today's price_snapshots."
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
