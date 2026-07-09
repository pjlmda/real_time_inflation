import csv

import pytest

from seed import load_seed
from tests.fake_supabase import FakeSupabaseClient

PRODUCTS_FIELDS = [
    "product_key",
    "canonical_name",
    "brand",
    "is_store_brand",
    "ecoicop2_code",
    "ean",
    "package_size",
    "package_unit",
]
LISTINGS_FIELDS = ["store_slug", "product_key", "store_sku", "ean", "url", "match_method"]


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_get_id_returns_matching_row_id():
    client = FakeSupabaseClient()
    client.table("categories").select_results.append([{"id": 7}])

    result = load_seed._get_id(client, "categories", {"ecoicop2_code": "01.1.1.1"})

    assert result == 7


def test_get_id_raises_when_no_match():
    client = FakeSupabaseClient()
    client.table("categories").select_results.append([])

    with pytest.raises(ValueError, match="No row in categories"):
        load_seed._get_id(client, "categories", {"ecoicop2_code": "99.9.9.9"})


def test_seed_products_and_listings_upserts_products_and_listings(tmp_path, monkeypatch):
    products_csv = tmp_path / "products.csv"
    listings_csv = tmp_path / "listings.csv"
    _write_csv(
        products_csv,
        PRODUCTS_FIELDS,
        [
            {
                "product_key": "p1",
                "canonical_name": "Widget A",
                "brand": "BrandX",
                "is_store_brand": "false",
                "ecoicop2_code": "01.1.1.1",
                "ean": "1111111111111",
                "package_size": "1",
                "package_unit": "kg",
            },
            {
                "product_key": "p2",
                "canonical_name": "Widget B",
                "brand": "BrandY",
                "is_store_brand": "true",
                "ecoicop2_code": "01.1.1.2",
                "ean": "TODO",
                "package_size": "0.5",
                "package_unit": "L",
            },
        ],
    )
    _write_csv(
        listings_csv,
        LISTINGS_FIELDS,
        [
            {
                "store_slug": "continente",
                "product_key": "p1",
                "store_sku": "SKU1",
                "ean": "1111111111111",
                "url": "https://continente.pt/p1",
                "match_method": "ean",
            },
            {
                "store_slug": "continente",
                "product_key": "p2",
                "store_sku": "TODO",
                "ean": "TODO",
                "url": "TODO",
                "match_method": "manual",
            },
            {
                "store_slug": "pingo-doce",
                "product_key": "p1",
                "store_sku": "SKU9",
                "ean": "1111111111111",
                "url": "https://pingodoce.pt/p1",
                "match_method": "ean",
            },
        ],
    )
    monkeypatch.setattr(load_seed, "PRODUCTS_CSV", products_csv)
    monkeypatch.setattr(load_seed, "LISTINGS_CSV", listings_csv)

    client = FakeSupabaseClient()
    # Category lookups happen once per product row, in CSV order (01.1.1.1 -> 10, 01.1.1.2 -> 20).
    client.table("categories").select_results = [[{"id": 10}], [{"id": 20}]]
    # Store lookups are cached by slug, so only the first listing for each new
    # slug triggers a lookup: continente (row 1), then pingo-doce (row 3).
    client.table("stores").select_results = [[{"id": 100}], [{"id": 200}]]

    load_seed.seed_products_and_listings(client)

    product_upserts = client.tables["products"].calls
    assert len(product_upserts) == 2
    assert product_upserts[0].payload == {
        "canonical_name": "Widget A",
        "brand": "BrandX",
        "is_store_brand": False,
        "category_id": 10,
        "ean": "1111111111111",
        "package_size": 1.0,
        "package_unit": "kg",
    }
    assert product_upserts[1].payload == {
        "canonical_name": "Widget B",
        "brand": "BrandY",
        "is_store_brand": True,
        "category_id": 20,
        "ean": None,
        "package_size": 0.5,
        "package_unit": "L",
    }

    listing_upserts = client.tables["product_listings"].calls
    assert len(listing_upserts) == 3
    # p1 at continente: fully curated (real URL) -> is_active True, product_id
    # resolved from the first product upsert's auto-assigned id (1).
    assert listing_upserts[0].payload["product_id"] == 1
    assert listing_upserts[0].payload["store_id"] == 100
    assert listing_upserts[0].payload["is_active"] is True
    assert listing_upserts[0].payload["store_sku"] == "SKU1"
    # p2 at continente: url still "TODO" -> not yet curated -> is_active False.
    assert listing_upserts[1].payload["product_id"] == 2
    assert listing_upserts[1].payload["is_active"] is False
    assert listing_upserts[1].payload["store_sku"] is None
    # p1 at pingo-doce: second store, looked up once and reused.
    assert listing_upserts[2].payload["store_id"] == 200
    assert listing_upserts[2].payload["product_id"] == 1
