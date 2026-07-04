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

LISBON_TZ = ZoneInfo("Europe/Lisbon")


def lisbon_scrape_date() -> str:
    """`scrape_date` must be a fixed Europe/Lisbon calendar date regardless of
    which machine/timezone runs the code — `date.today()` uses the ambient
    system timezone, which differs between a local dev machine and GitHub
    Actions' UTC runners and silently breaks the one-row-per-listing-per-day
    idempotency guarantee across environments."""
    return datetime.now(LISBON_TZ).date().isoformat()


class SupabaseWriter:
    def __init__(self, client):
        self.client = client

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
        today = lisbon_scrape_date()
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
            "scrape_date": lisbon_scrape_date(),
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
        today = lisbon_scrape_date()
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
            "scrape_date": lisbon_scrape_date(),
            "n_products": stats.n_products,
            "median_price_per_unit": stats.median,
            "mean_price_per_unit": stats.mean,
            "p25_price_per_unit": stats.p25,
            "p75_price_per_unit": stats.p75,
        }
        self.client.table("category_observations").upsert(
            row, on_conflict="store_id,category_id,scrape_date"
        ).execute()
