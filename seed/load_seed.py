"""Idempotent seed orchestrator: stores -> categories -> products -> listings.

products.csv holds canonical product definitions (one row per physical good,
keyed by a human-readable `product_key`); listings.csv holds one row per
store-specific listing of that product, referencing it by `product_key`.
Splitting them this way is what makes cross-store matching possible: two
listings.csv rows can point at the same product_key when the same physical
product (same manufacturer, same EAN) is sold at two different stores.

Usage: `python -m seed.load_seed`
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from seed.categories import seed_categories
from seed.stores import seed_stores

PRODUCTS_CSV = Path(__file__).resolve().parent / "products.csv"
LISTINGS_CSV = Path(__file__).resolve().parent / "listings.csv"


def _get_id(supabase_client, table: str, match: dict, select: str = "id") -> int:
    resp = supabase_client.table(table).select(select).match(match).limit(1).execute()
    if not resp.data:
        raise ValueError(f"No row in {table} matching {match}")
    return resp.data[0]["id"]


def seed_products_and_listings(supabase_client) -> None:
    with PRODUCTS_CSV.open(encoding="utf-8") as f:
        product_rows = list(csv.DictReader(f))
    with LISTINGS_CSV.open(encoding="utf-8") as f:
        listing_rows = list(csv.DictReader(f))

    product_id_by_key: dict[str, int] = {}
    for row in product_rows:
        category_id = _get_id(
            supabase_client, "categories", {"ecoicop2_code": row["ecoicop2_code"]}
        )
        product_row = {
            "canonical_name": row["canonical_name"],
            "brand": row["brand"],
            "is_store_brand": row["is_store_brand"].lower() == "true",
            "category_id": category_id,
            "ean": None if row["ean"] == "TODO" else row["ean"],
            "package_size": float(row["package_size"]),
            "package_unit": row["package_unit"],
        }
        resp = (
            supabase_client.table("products")
            .upsert(product_row, on_conflict="canonical_name,brand")
            .execute()
        )
        product_id_by_key[row["product_key"]] = resp.data[0]["id"]

    store_id_by_slug: dict[str, int] = {}
    for row in listing_rows:
        slug = row["store_slug"]
        if slug not in store_id_by_slug:
            store_id_by_slug[slug] = _get_id(supabase_client, "stores", {"slug": slug})

        product_id = product_id_by_key[row["product_key"]]
        is_curated = row["url"] != "TODO"

        listing_row = {
            "product_id": product_id,
            "store_id": store_id_by_slug[slug],
            "store_sku": None if row["store_sku"] == "TODO" else row["store_sku"],
            "ean": None if row["ean"] == "TODO" else row["ean"],
            "url": row["url"],
            "match_method": row["match_method"],
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
