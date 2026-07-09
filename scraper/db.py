"""Supabase read/write wrapper for the scraper (spec §4.5, §4.8).

Uses `supabase-py` (PostgREST over HTTPS) rather than a raw Postgres driver:
the write pattern here is simple per-table upserts/inserts, which is exactly
what PostgREST's `upsert(..., on_conflict=...)` handles well, and it needs no
connection-string/pooling/IP-allowlist setup to run from GitHub Actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scraper.models import CategoryStats, Listing, RunResult, ScrapedPrice

# Portugal is WET/WEST (UTC+0/+1); most of the rest of Western Europe,
# including France, is CET/CEST (UTC+1/+2) — a genuine one-hour gap
# year-round, not a DST rounding quirk. scrape_date must be pinned to each
# *store's own* timezone (StoreConfig.timezone_id), not a single global
# constant — a French store inheriting Portugal's midnight would get its
# day boundary silently wrong (docs/france-expansion-plan.md §3.3).
DEFAULT_TIMEZONE_ID = "Europe/Lisbon"


def scrape_date_for_timezone(timezone_id: str = DEFAULT_TIMEZONE_ID) -> str:
    """`scrape_date` must be a fixed calendar date in the store's own
    timezone regardless of which machine runs the code — `date.today()` uses
    the ambient system timezone, which differs between a local dev machine
    and GitHub Actions' UTC runners and silently breaks the
    one-row-per-listing-per-day idempotency guarantee across environments."""
    return datetime.now(ZoneInfo(timezone_id)).date().isoformat()


def is_same_day(iso_timestamp: str, timezone_id: str = DEFAULT_TIMEZONE_ID) -> bool:
    """Whether a stored UTC timestamp (e.g. `scrape_runs.started_at`) falls on
    today's calendar date in the given timezone — used to decide if a
    same-day retry should skip a store that was blocked earlier today,
    without a `scrape_date` column on `scrape_runs` itself to compare
    against directly."""
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(timezone_id)).date().isoformat() == scrape_date_for_timezone(timezone_id)


class SupabaseWriter:
    def __init__(self, client, timezone_id: str = DEFAULT_TIMEZONE_ID):
        self.client = client
        self.timezone_id = timezone_id

    def get_store_id(self, slug: str) -> int:
        resp = self.client.table("stores").select("id").eq("slug", slug).limit(1).execute()
        return resp.data[0]["id"]

    def get_active_listings(self, store_id: int) -> list[Listing]:
        resp = (
            self.client.table("product_listings")
            .select("id, product_id, store_id, url, store_sku")
            .eq("store_id", store_id)
            .eq("is_active", True)
            .execute()
        )
        return [Listing(**row) for row in resp.data]

    def listing_already_captured_today(self, listing_id: int) -> bool:
        today = scrape_date_for_timezone(self.timezone_id)
        resp = (
            self.client.table("price_snapshots")
            .select("id")
            .eq("listing_id", listing_id)
            .eq("scrape_date", today)
            .limit(1)
            .execute()
        )
        return len(resp.data) > 0

    def upsert_snapshot(self, listing_id: int, scraped: ScrapedPrice) -> None:
        row = {
            "listing_id": listing_id,
            "scrape_date": scrape_date_for_timezone(self.timezone_id),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "price": scraped.price,
            "regular_price": scraped.regular_price,
            "price_per_unit": scraped.price_per_unit,
            "unit_basis": scraped.unit_basis,
            "is_promotion": scraped.is_promotion,
            "promotion_label": scraped.promotion_label,
            "in_stock": scraped.in_stock,
            "currency": "EUR",
            "raw_payload": scraped.raw_payload,
        }
        self.client.table("price_snapshots").upsert(
            row, on_conflict="listing_id,scrape_date"
        ).execute()

    def start_run(self, store_id: int, mode: str) -> int:
        resp = (
            self.client.table("scrape_runs")
            .insert({"store_id": store_id, "mode": mode, "status": "success"})
            .execute()
        )
        return resp.data[0]["id"]

    def get_latest_run(self, store_id: int, mode: str) -> dict | None:
        """Most recent scrape_runs row for this store+mode (any date) — used to
        decide whether a same-day retry should skip a store blocked earlier
        today (spec §7: don't retry into an active block)."""
        resp = (
            self.client.table("scrape_runs")
            .select("blocked, started_at")
            .eq("store_id", store_id)
            .eq("mode", mode)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def finish_run(self, result: RunResult) -> None:
        self.client.table("scrape_runs").update(
            {
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "listings_attempted": result.attempted,
                "listings_ok": result.ok,
                "listings_failed": result.failed,
                "status": result.status,
                "coverage": result.coverage,
                "error_summary": result.error_summary,
                "blocked": result.blocked,
            }
        ).eq("id", result.run_id).execute()

    def mark_alerted(self, run_id: int) -> None:
        self.client.table("scrape_runs").update({"alerted": True}).eq("id", run_id).execute()

    def update_robots_checked(self, store_id: int) -> None:
        self.client.table("stores").update(
            {"robots_checked_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", store_id).execute()

    def get_category_id(self, ecoicop2_code: str) -> int:
        resp = (
            self.client.table("categories")
            .select("id")
            .eq("ecoicop2_code", ecoicop2_code)
            .limit(1)
            .execute()
        )
        return resp.data[0]["id"]

    def category_already_captured_today(self, store_id: int, category_id: int) -> bool:
        today = scrape_date_for_timezone(self.timezone_id)
        resp = (
            self.client.table("category_observations")
            .select("id")
            .eq("store_id", store_id)
            .eq("category_id", category_id)
            .eq("scrape_date", today)
            .limit(1)
            .execute()
        )
        return len(resp.data) > 0

    def upsert_category_observation(
        self, store_id: int, category_id: int, stats: CategoryStats
    ) -> None:
        row = {
            "store_id": store_id,
            "category_id": category_id,
            "scrape_date": scrape_date_for_timezone(self.timezone_id),
            "n_products": stats.n_products,
            "median_price_per_unit": stats.median,
            "mean_price_per_unit": stats.mean,
            "p25_price_per_unit": stats.p25,
            "p75_price_per_unit": stats.p75,
        }
        self.client.table("category_observations").upsert(
            row, on_conflict="store_id,category_id,scrape_date"
        ).execute()
