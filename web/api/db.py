"""Read-only Supabase access for the web API.

Self-contained on purpose: Vercel's Python function build is scoped to the
project's Root Directory (`web/`), so this can't import the repo-root
`scraper`/`metrics` packages even if it wanted to — it has its own minimal
client and query helpers.

Holds `SUPABASE_SERVICE_KEY` server-side only (a Vercel environment
variable, never shipped to the browser) — the "backend holds the service
key" pattern, avoiding any need for Row Level Security policies for a
public read-only API.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dotenv import load_dotenv
from supabase import Client, create_client

ACTIVE_STORES = ["continente", "pingo-doce", "auchan"]
COVERAGE_ALERT_THRESHOLD = 0.85
STALE_AFTER_HOURS = 36


@lru_cache
def get_client() -> Client:
    # No-op in production (Vercel injects env vars directly, and load_dotenv
    # never overrides an already-set variable) — only meaningful for local dev.
    load_dotenv()
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _is_stale(iso_timestamp: str | None) -> bool:
    if not iso_timestamp:
        return True
    ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - ts) > timedelta(hours=STALE_AFTER_HOURS)


class SupabaseReader:
    def __init__(self, client: Client | None = None):
        self.client = client or get_client()

    # --- /health ---

    def get_health(self) -> dict:
        stores: dict[str, dict] = {}
        healthy = True
        for slug in ACTIVE_STORES:
            store_resp = self.client.table("stores").select("id").eq("slug", slug).limit(1).execute()
            if not store_resp.data:
                continue
            store_id = store_resp.data[0]["id"]
            per_mode: dict[str, dict | None] = {}
            for mode in ("basket", "category"):
                resp = (
                    self.client.table("scrape_runs")
                    .select("status, coverage, finished_at, blocked")
                    .eq("store_id", store_id)
                    .eq("mode", mode)
                    .order("started_at", desc=True)
                    .limit(1)
                    .execute()
                )
                row = resp.data[0] if resp.data else None
                per_mode[mode] = row
                if row is None or row["status"] == "failed" or (row["coverage"] or 0) < COVERAGE_ALERT_THRESHOLD:
                    healthy = False
            stores[slug] = per_mode

        compute_resp = (
            self.client.table("inflation_metrics").select("computed_at").order("computed_at", desc=True).limit(1).execute()
        )
        latest_computed_at = compute_resp.data[0]["computed_at"] if compute_resp.data else None
        compute_stale = _is_stale(latest_computed_at)

        fuel_resp = self.client.table("fuel_prices").select("fetched_at").order("fetched_at", desc=True).limit(1).execute()
        latest_fetched_at = fuel_resp.data[0]["fetched_at"] if fuel_resp.data else None
        fuel_stale = _is_stale(latest_fetched_at)

        return {
            "healthy": healthy and not compute_stale,
            "stores": stores,
            "compute": {"latest_computed_at": latest_computed_at, "stale": compute_stale},
            "fuel": {"latest_fetched_at": latest_fetched_at, "stale": fuel_stale},
        }

    # --- /inflation/latest ---

    def get_latest_as_of_date(self) -> str | None:
        resp = self.client.table("inflation_metrics").select("as_of_date").order("as_of_date", desc=True).limit(1).execute()
        return resp.data[0]["as_of_date"] if resp.data else None

    def get_latest_overall(self) -> dict:
        as_of_date = self.get_latest_as_of_date()
        if as_of_date is None:
            return {"as_of_date": None, "fixed_basket": {}, "category_avg": {}}

        resp = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "overall")
            .execute()
        )
        result: dict = {"as_of_date": as_of_date, "fixed_basket": {}, "category_avg": {}}
        for row in resp.data:
            family = row["index_family"]
            basis = row["price_basis"]
            result.setdefault(family, {}).setdefault(basis, {})[row["period"]] = _shape_metric_row(row)
        return result

    # --- /inflation/series ---

    def get_series(
        self, family: str, dimension: str, dimension_value: str, period: str, basis: str
    ) -> list[dict]:
        resp = (
            self.client.table("inflation_metrics")
            .select("as_of_date, index_value, index_value_ma7, inflation_rate, n_products, coverage")
            .eq("index_family", family)
            .eq("dimension", dimension)
            .eq("dimension_value", dimension_value)
            .eq("period", period)
            .eq("price_basis", basis)
            .order("as_of_date")
            .execute()
        )
        return [_shape_metric_row(row) | {"as_of_date": row["as_of_date"]} for row in resp.data]

    # --- /categories ---

    def get_categories(self) -> list[dict]:
        categories = self.client.table("categories").select("*").order("ecoicop2_code").execute().data
        as_of_date = self.get_latest_as_of_date()
        latest = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "category")
            .eq("period", "daily")
            .execute()
            .data
            if as_of_date
            else []
        )
        by_code: dict[str, dict] = {}
        for row in latest:
            by_code.setdefault(row["dimension_value"], {})[f"{row['index_family']}_{row['price_basis']}"] = (
                _shape_metric_row(row)
            )

        # Each category's index is rebased to 100 on the first day it entered
        # the tracker (categories were added incrementally across several
        # basket-growth rounds, not all on day one) — surfaced per-category so
        # the "Index" column can be traced back to a concrete base date rather
        # than a single project-wide one.
        base_dates_resp = (
            self.client.table("inflation_metrics")
            .select("dimension_value, as_of_date")
            .eq("dimension", "category")
            .eq("index_family", "fixed_basket")
            .eq("price_basis", "headline")
            .eq("period", "daily")
            .order("as_of_date")
            .execute()
            .data
        )
        base_date_by_code: dict[str, str] = {}
        for row in base_dates_resp:
            base_date_by_code.setdefault(row["dimension_value"], row["as_of_date"])

        return [
            {
                "ecoicop2_code": cat["ecoicop2_code"],
                "name_pt": cat["name_pt"],
                "name_en": cat["name_en"],
                "hicp_weight": cat["hicp_weight"],
                "latest": by_code.get(cat["ecoicop2_code"], {}),
                "base_date": base_date_by_code.get(cat["ecoicop2_code"]),
            }
            for cat in categories
        ]

    # --- /inflation/series/bulk ---

    def get_category_series_bulk(self, family: str, period: str, basis: str) -> dict[str, list[dict]]:
        # One round trip for every category's series, instead of the N
        # separate /inflation/series calls a personalized-weights view would
        # otherwise need (see docs/future-roadmap.md Part 1).
        resp = (
            self.client.table("inflation_metrics")
            .select("dimension_value, as_of_date, index_value, index_value_ma7")
            .eq("dimension", "category")
            .eq("index_family", family)
            .eq("period", period)
            .eq("price_basis", basis)
            .order("as_of_date")
            .execute()
            .data
        )
        by_code: dict[str, list[dict]] = {}
        for row in resp:
            by_code.setdefault(row["dimension_value"], []).append(
                {
                    "as_of_date": row["as_of_date"],
                    "index_value": row["index_value"],
                    "index_value_ma7": row["index_value_ma7"],
                }
            )
        return by_code

    # --- /stores ---

    def get_stores(self) -> list[dict]:
        # `stores` has no is_active column (only config/stores.yaml's `active`
        # flag, not persisted) — filter to the stores actually being scraped.
        stores = self.client.table("stores").select("*").in_("slug", ACTIVE_STORES).execute().data
        as_of_date = self.get_latest_as_of_date()
        latest = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "store")
            .eq("period", "daily")
            .execute()
            .data
            if as_of_date
            else []
        )
        by_slug: dict[str, dict] = {}
        for row in latest:
            by_slug.setdefault(row["dimension_value"], {})[f"{row['index_family']}_{row['price_basis']}"] = (
                _shape_metric_row(row)
            )

        result = []
        for store in stores:
            slug = store["slug"]
            latest_run = (
                self.client.table("scrape_runs")
                .select("status, coverage, finished_at")
                .eq("store_id", store["id"])
                .eq("mode", "basket")
                .order("started_at", desc=True)
                .limit(1)
                .execute()
                .data
            )
            result.append(
                {
                    "slug": slug,
                    "name": store["name"],
                    "latest": by_slug.get(slug, {}),
                    "last_scrape": latest_run[0] if latest_run else None,
                }
            )
        return result

    # --- /products ---

    def get_products(self) -> list[dict]:
        products = self.client.table("products").select("*, categories(ecoicop2_code, name_en)").eq("is_active", True).execute().data
        listings = (
            self.client.table("product_listings")
            .select("*, stores(slug)")
            .eq("is_active", True)
            .execute()
            .data
        )
        listing_ids = [listing["id"] for listing in listings]
        latest_snapshots: dict[int, dict] = {}
        if listing_ids:
            snapshots = (
                self.client.table("price_snapshots")
                .select("listing_id, scrape_date, price, regular_price, price_per_unit, unit_basis, is_promotion")
                .in_("listing_id", listing_ids)
                .order("scrape_date", desc=True)
                .execute()
                .data
            )
            for snap in snapshots:
                latest_snapshots.setdefault(snap["listing_id"], snap)

        listings_by_product: dict[int, list[dict]] = {}
        for listing in listings:
            snap = latest_snapshots.get(listing["id"])
            listings_by_product.setdefault(listing["product_id"], []).append(
                {
                    "store": listing["stores"]["slug"],
                    "url": listing["url"],
                    "latest_price": snap,
                }
            )

        return [
            {
                "canonical_name": product["canonical_name"],
                "brand": product["brand"],
                "category": product["categories"]["ecoicop2_code"] if product.get("categories") else None,
                "package_size": product["package_size"],
                "package_unit": product["package_unit"],
                "listings": listings_by_product.get(product["id"], []),
            }
            for product in products
        ]

    # --- /fuel/latest ---

    def get_fuel_latest(self) -> list[dict]:
        rows = self.client.table("fuel_prices").select("*").order("scrape_date", desc=True).execute().data
        by_fuel_type: dict[str, list[dict]] = {}
        for row in rows:
            by_fuel_type.setdefault(row["fuel_type"], []).append(row)

        result = []
        for fuel_type, history in by_fuel_type.items():
            latest = history[0]
            week_ago_date = (
                datetime.fromisoformat(latest["scrape_date"]).date() - timedelta(days=7)
            ).isoformat()
            week_ago = next((r for r in history if r["scrape_date"] <= week_ago_date), None)
            result.append(
                {
                    "fuel_type": fuel_type,
                    "scrape_date": latest["scrape_date"],
                    "price": latest["price"],
                    "unit": latest["unit"],
                    "week_ago_price": week_ago["price"] if week_ago else None,
                }
            )
        return result


def _shape_metric_row(row: dict) -> dict:
    coverage = row.get("coverage")
    return {
        "index_value": row.get("index_value"),
        "index_value_ma7": row.get("index_value_ma7"),
        "inflation_rate": row.get("inflation_rate"),
        "n_products": row.get("n_products"),
        "coverage": coverage,
        "low_confidence": (coverage is not None and coverage < COVERAGE_ALERT_THRESHOLD),
    }
