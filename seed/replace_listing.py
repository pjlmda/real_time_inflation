"""Reusable helper for replacing a dead product_listings row with a live
replacement — a playbook this project didn't have checked in yet (the only
precedent, deactivating all 30 Lidl France listings on 2026-07-23, was done
ad hoc directly against production, documented only after the fact in
seed/README.md).

Two write shapes:

  - replace_with_new_product() (insert-shape): the general case — the
    replacement is a genuinely different retail unit (pack size, brand, or
    variety) than the dead listing. product_listings' `unique(product_id,
    store_id)` constraint has no `where is_active` filter, so a second
    listing row for the SAME product_id+store_id is rejected regardless of
    the old row's is_active status (and the old row can never be deleted —
    price_snapshots references it and is append-only) — a new product_id is
    the only way to satisfy the constraint. It's also the *correct* choice
    whenever the retail unit changed: metrics/compute.py's price relative is
    price_t / price_0 on the absolute price column, not price-per-unit, so
    reusing a listing_id across a pack/brand/size substitution would inject
    a fake price step-change (or, as found live during this round - see
    Pingo Doce below - silently hide a real one).

  - update_listing_in_place() (no insert): only for a verified, literal
    same-product re-issued under a new store SKU/URL with NO change to pack
    size/brand. No insert happens, so the unique constraint never applies,
    and it preserves that listing's full price history/day-0 base across
    the outage gap. Not used by any item in this round's actual batch (see
    module-level `main()` below) — Pingo Doce's lettuce was originally
    assumed to qualify, but live re-verification found its replacement SKU
    is a 300g pack, not the original 400g, so it went through the
    insert-shape path instead: reusing the listing there would have made a
    real ~25% per-unit price increase look like zero change in the index.

Deliberately uses plain `.insert()`, not `.upsert()`, for both new-row
writes: unlike load_seed.py's routine idempotent reseeding, a collision
here (an accidental canonical_name/brand match, or a product_id+store_id
pair that isn't actually new) should fail loudly, not silently merge into
an unrelated existing row.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class NewProduct:
    canonical_name: str
    brand: str | None
    is_store_brand: bool
    ecoicop2_code: str
    package_size: float
    package_unit: str
    ean: str | None


@dataclass(frozen=True)
class NewListing:
    store_slug: str
    url: str
    store_sku: str | None
    ean: str | None
    match_method: str


def _get_id(client, table: str, match: dict, select: str = "id") -> int:
    resp = client.table(table).select(select).match(match).limit(1).execute()
    if not resp.data:
        raise ValueError(f"No row in {table} matching {match}")
    return resp.data[0]["id"]


def deactivate_listing(client, listing_id: int, *, expected_store_slug: str) -> None:
    """Deactivates listing_id, but only after confirming it actually
    belongs to expected_store_slug. A security review of this module's
    first real run flagged that a bare `.update().eq("id", listing_id)`
    would silently deactivate a *healthy* listing on a typo'd id, reporting
    success either way - this is the guard against that, not optional."""
    store_id = _get_id(client, "stores", {"slug": expected_store_slug})
    listing = client.table("product_listings").select("id,store_id").eq("id", listing_id).limit(1).execute().data
    if not listing:
        raise ValueError(f"No product_listings row with id={listing_id} to deactivate")
    if listing[0]["store_id"] != store_id:
        raise ValueError(
            f"Refusing to deactivate listing {listing_id}: belongs to store_id="
            f"{listing[0]['store_id']}, not {expected_store_slug!r} (store_id={store_id})"
        )
    resp = client.table("product_listings").update({"is_active": False}).eq("id", listing_id).execute()
    if not resp.data:
        raise ValueError(f"No product_listings row with id={listing_id} to deactivate")


def insert_replacement_product(client, product: NewProduct) -> int:
    category_id = _get_id(client, "categories", {"ecoicop2_code": product.ecoicop2_code})
    row = {
        "canonical_name": product.canonical_name,
        "brand": product.brand,
        "is_store_brand": product.is_store_brand,
        "category_id": category_id,
        "ean": product.ean,
        "package_size": product.package_size,
        "package_unit": product.package_unit,
    }
    resp = client.table("products").insert(row).execute()
    return resp.data[0]["id"]


def insert_replacement_listing(client, product_id: int, listing: NewListing) -> int:
    store_id = _get_id(client, "stores", {"slug": listing.store_slug})
    row = {
        "product_id": product_id,
        "store_id": store_id,
        "store_sku": listing.store_sku,
        "ean": listing.ean,
        "url": listing.url,
        "match_method": listing.match_method,
        "is_active": True,
    }
    resp = client.table("product_listings").insert(row).execute()
    return resp.data[0]["id"]


def replace_with_new_product(
    client, old_listing_id: int, new_product: NewProduct, new_listing: NewListing
) -> tuple[int, int]:
    product_id = insert_replacement_product(client, new_product)
    listing_id = insert_replacement_listing(client, product_id, new_listing)
    # A replacement always targets the same store as what it's replacing -
    # new_listing.store_slug doubles as the expected store for the
    # deactivation, no separate parameter needed.
    deactivate_listing(client, old_listing_id, expected_store_slug=new_listing.store_slug)
    return product_id, listing_id


def update_listing_in_place(client, listing_id: int, url: str, store_sku: str | None) -> None:
    resp = (
        client.table("product_listings")
        .update({"url": url, "store_sku": store_sku, "is_active": True})
        .eq("id", listing_id)
        .execute()
    )
    if not resp.data:
        raise ValueError(f"No product_listings row with id={listing_id} to update")


def main() -> None:
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # 2026-08-23 dead-listing replacement round. All URLs/SKUs/EANs live
    # re-verified this session (not carried over from the original 2026-08-22
    # research unchecked) - see seed/README.md for the full per-item
    # reasoning and what changed between the two passes.

    # 1. Continente listing 16: Leite UHT Inteiro Mimosa 1L -> 6-pack.
    # Different pack size (1L -> 6L) -> insert-shape. Does NOT touch
    # product_id=16's row itself - that product is shared with a still-live
    # Pingo Doce listing (id=38) and must be left untouched; only
    # Continente's own listing 16 deactivates.
    pid, lid = replace_with_new_product(
        client,
        old_listing_id=16,
        new_product=NewProduct(
            canonical_name="Leite UHT Inteiro Mimosa 6x1L",
            brand="Mimosa",
            is_store_brand=False,
            ecoicop2_code="01.1.4.1",
            package_size=6,
            package_unit="L",
            ean=None,  # not exposed in Continente's JSON-LD for this SKU (confirmed live)
        ),
        new_listing=NewListing(
            store_slug="continente",
            url="https://www.continente.pt/produto/leite-uht-inteiro-mimosa-mimosa-4362757.html",
            store_sku="4362757",
            ean=None,
            match_method="manual",  # no EAN available, so 'ean' match_method would be dishonest
        ),
    )
    print(f"Continente milk: new product_id={pid}, new listing_id={lid}, old listing 16 deactivated.")

    # 2. Pingo Doce listing 307: Alface Iceberg Embalada -> re-issued SKU.
    # Originally assumed to be a literal same-product SKU reissue (planned
    # update-in-place) - live re-verification this session found the URL
    # 301-redirects to a renamed product ("Salada Iceberg Embalada",
    # description "SALADA ICEBE 300G PD") that is genuinely smaller than the
    # dead listing's 400g (products.id=259: package_size=0.4kg). A real
    # pack-size shrink -> insert-shape, same reasoning as #1: reusing the
    # listing would have made a real ~25% per-unit price increase read as
    # zero change in the index.
    pid, lid = replace_with_new_product(
        client,
        old_listing_id=307,
        new_product=NewProduct(
            canonical_name="Salada Iceberg Embalada Pingo Doce",
            brand="Pingo Doce",
            is_store_brand=True,
            ecoicop2_code="01.1.7.1",
            package_size=0.3,
            package_unit="kg",
            ean=None,  # Pingo Doce never exposes EAN, same as every other PD listing
        ),
        new_listing=NewListing(
            store_slug="pingo-doce",
            url=(
                "https://www.pingodoce.pt/home/produtos/frutas-e-vegetais/vegetais/"
                "saladas-e-legumes-preparados/salada-iceberg-embalada-pingo-doce-725572.html"
            ),
            store_sku="725572",
            ean=None,
            match_method="manual",
        ),
    )
    print(f"Pingo Doce lettuce: new product_id={pid}, new listing_id={lid}, old listing 307 deactivated.")

    # 3. Auchan PT listing 300: Pera Rocha -> Pera Morettinni (different variety).
    pid, lid = replace_with_new_product(
        client,
        old_listing_id=300,
        new_product=NewProduct(
            canonical_name="Pera Morettinni Auchan",
            brand="Auchan",
            is_store_brand=True,
            ecoicop2_code="01.1.6.1",
            package_size=1,
            package_unit="kg",
            ean="2886222000008",
        ),
        new_listing=NewListing(
            store_slug="auchan",
            url="https://www.auchan.pt/pt/produtos-frescos/fruta/fruta-da-epoca/pera-morettinni-auchan-kg/3356399.html",
            store_sku="3356399",
            ean="2886222000008",
            match_method="ean",
        ),
    )
    print(f"Auchan pear: new product_id={pid}, new listing_id={lid}, old listing 300 deactivated.")

    # 4. Auchan PT listing 308: Alface Iceberg (loose, kg) -> Auchan 200g
    # fixed pack. package_unit changes kg->effectively a fixed-weight pack
    # (modeled here as 0.2kg to stay consistent with this store's existing
    # kg-based convention for vegetables) -> insert-shape.
    pid, lid = replace_with_new_product(
        client,
        old_listing_id=308,
        new_product=NewProduct(
            canonical_name="Alface Iceberg Auchan 200g",
            brand="Auchan",
            is_store_brand=True,
            ecoicop2_code="01.1.7.1",
            package_size=0.2,
            package_unit="kg",
            ean="5601002125279",
        ),
        new_listing=NewListing(
            store_slug="auchan",
            url="https://www.auchan.pt/pt/produtos-frescos/legumes/alface-e-agriao/alface-iceberg-auchan-200-g/3799843.html",
            store_sku="3799843",
            ean="5601002125279",
            match_method="ean",
        ),
    )
    print(f"Auchan lettuce: new product_id={pid}, new listing_id={lid}, old listing 308 deactivated.")

    # 5. Wegmans Rotini (product_id=1035, dead SKU 48985) -> Barilla Rotini
    # (SKU 531336, live-confirmed sold at all 4 tracked locations). Real
    # finding not in the original research: rotini_wegmans_us is shared
    # across all four Wegmans locations (listings 1236/1820/1878/2315 -
    # medford/nyc/fairfax/chapelhill), all four dead, not just one -> one
    # new product_id, four new listings, four deactivations.
    new_rotini_product = NewProduct(
        canonical_name="Barilla Rotini Pasta",
        brand="Barilla",
        is_store_brand=False,
        ecoicop2_code="01.1.1.6",
        package_size=454,
        package_unit="g",
        ean="00076808280982",
    )
    category_id = _get_id(client, "categories", {"ecoicop2_code": new_rotini_product.ecoicop2_code})
    rotini_product_id = client.table("products").insert(
        {
            "canonical_name": new_rotini_product.canonical_name,
            "brand": new_rotini_product.brand,
            "is_store_brand": new_rotini_product.is_store_brand,
            "category_id": category_id,
            "ean": new_rotini_product.ean,
            "package_size": new_rotini_product.package_size,
            "package_unit": new_rotini_product.package_unit,
        }
    ).execute().data[0]["id"]
    print(f"Wegmans Barilla Rotini: new product_id={rotini_product_id}.")

    wegmans_old_listing_ids = {
        "wegmans-us-medford": 1236,
        "wegmans-us-nyc": 1820,
        "wegmans-us-fairfax": 1878,
        "wegmans-us-chapelhill": 2315,
    }
    for store_slug, old_listing_id in wegmans_old_listing_ids.items():
        listing_id = insert_replacement_listing(
            client,
            rotini_product_id,
            NewListing(
                store_slug=store_slug,
                url="https://www.wegmans.com/shop/product/531336-Rotini-Pasta",
                store_sku="531336",
                ean="00076808280982",
                match_method="ean",
            ),
        )
        deactivate_listing(client, old_listing_id, expected_store_slug=store_slug)
        print(f"  {store_slug}: new listing_id={listing_id}, old listing {old_listing_id} deactivated.")


if __name__ == "__main__":
    main()
