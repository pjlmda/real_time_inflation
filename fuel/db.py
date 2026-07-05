"""Supabase writer for `fuel_prices` (Part C — first prototype).

Kept separate from `scraper.db.SupabaseWriter` — that class's whole shape
(store_id, listing idempotency, scrape_runs lifecycle) is grocery-specific
and doesn't apply to a national fuel average with no store/product concept.
"""
from __future__ import annotations

# DGEG's Portuguese unit label -> our EUR/<unit> suffix.
UNIT_ABBREV_MAP = {"litro": "L", "kg": "kg", "m3": "m3"}


def upsert_fuel_price(client, fuel_type: str, row: dict) -> None:
    unit = UNIT_ABBREV_MAP.get(row["unit"].lower(), row["unit"])
    payload = {
        "fuel_type": fuel_type,
        "scrape_date": row["date"],
        "price": row["price"],
        "unit": f"EUR/{unit}",
        "source": "dgeg_national_average",
        "raw_payload": row,
    }
    client.table("fuel_prices").upsert(payload, on_conflict="fuel_type,scrape_date").execute()
