"""Supabase writer for `fuel_prices` (migration 0008 — multi-source/
multi-country). Kept separate from `scraper.db.SupabaseWriter` — that
class's whole shape (store_id, listing idempotency, scrape_runs
lifecycle) is grocery-specific and doesn't apply to a fuel average with
no store/product concept.

Deliberately does no currency/unit formatting of its own — each source
module owns normalizing its own raw output into the shared row shape
(fuel/dgeg.py's DGEG-label mapping via format_unit(), fuel/eia.py's
$/GAL normalization) before calling this, since the "right" unit differs
per source and a shared writer can't guess it. Previously this hardcoded
an 'EUR/' prefix unconditionally, which would have silently mislabeled
every US row's unit as EUR even though the price is USD.
"""
from __future__ import annotations

from datetime import datetime, timezone


def upsert_fuel_price(
    client, fuel_type: str, row: dict, *, country: str, source: str, region: str = "NATIONAL"
) -> None:
    payload = {
        "fuel_type": fuel_type,
        "scrape_date": row["date"],
        "price": row["price"],
        "unit": row["unit"],
        "country": country,
        "region": region,
        "source": source,
        "raw_payload": row,
        # Explicit, not left to the column's insert-only `now()` default:
        # a weekly source (fuel/eia.py) re-upserts the identical
        # (fuel_type, scrape_date, country, region) row on every run until
        # the underlying period changes, which is an UPDATE, not an
        # INSERT — the default would never fire again, so
        # web/api/db.py's staleness check would read "last inserted", not
        # "last successfully ran", and falsely report the row as stale
        # within days even on a perfectly healthy schedule.
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    client.table("fuel_prices").upsert(
        payload, on_conflict="fuel_type,scrape_date,country,region"
    ).execute()
