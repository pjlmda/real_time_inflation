"""Idempotent seed orchestrator: stores -> categories -> products/listings.

Usage: `python -m seed.load_seed`
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from seed.categories import seed_categories
from seed.stores import seed_stores

PRODUCTS_CSV = Path(__file__).resolve().parent / "products.csv"
CONTINENTE_SLUG = "continente"


def _get_id(supabase_client, table: str, match: dict, select: str = "id") -> int:
    resp = supabase_client.table(table).select(select).match(match).limit(1).execute()
    if not resp.data:
        raise ValueError(f"No row in {table} matching {match}")
    return resp.data[0]["id"]


def seed_products_and_listings(supabase_client) -> None:
    continente_id = _get_id(supabase_client, "stores", {"slug": CONTINENTE_SLUG})

    with PRODUCTS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        category_id = _get_id(
            supabase_client, "categories", {"ecoicop2_code": row["ecoicop2_code"]}
        )
        is_curated = row["continente_product_url"] != "TODO"

        product_row = {
            "canonical_name": row["canonical_name"],
            "brand": row["brand"],
            "is_store_brand": row["is_store_brand"].lower() == "true",
            "category_id": category_id,
            "ean": None if row["ean"] == "TODO" else row["ean"],
            "package_size": float(row["package_size"]),
            "package_unit": row["package_unit"],
        }
        product_resp = (
            supabase_client.table("products")
            .upsert(product_row, on_conflict="canonical_name,brand")
            .execute()
        )
        product_id = product_resp.data[0]["id"]

        listing_row = {
            "product_id": product_id,
            "store_id": continente_id,
            "store_sku": None if row["continente_sku"] == "TODO" else row["continente_sku"],
            "ean": None if row["ean"] == "TODO" else row["ean"],
            "url": row["continente_category_url"]
            if not is_curated
            else row["continente_product_url"],
            "raw_name": row["canonical_name"],
            "match_method": "manual",
            "is_active": is_curated,
        }
        supabase_client.table("product_listings").upsert(
            listing_row, on_conflict="product_id,store_id"
        ).execute()


def main() -> None:
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    seed_stores(client)
    seed_categories(client)
    seed_products_and_listings(client)
    print("Seed complete: stores, categories, products, product_listings.")


if __name__ == "__main__":
    main()
