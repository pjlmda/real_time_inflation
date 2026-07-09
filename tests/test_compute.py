import pytest

from metrics.compute import (
    _write_index_and_rates,
    base_and_current_price,
    class_relatives,
    fetch_basket_rows,
    fetch_category_weights,
)
from tests.fake_supabase import FakeSupabaseClient


def _basket_row(listing_id, ecoicop2_code="01.1.1.1", within_cat_weight=1.0):
    return {
        "id": listing_id,
        "products": {
            "within_cat_weight": within_cat_weight,
            "categories": {"ecoicop2_code": ecoicop2_code},
        },
    }


def test_base_and_current_price_uses_first_ever_snapshot_as_base():
    snapshots = [
        {"scrape_date": "2026-07-01", "price": 2.00, "regular_price": 2.20},
        {"scrape_date": "2026-07-02", "price": 2.20, "regular_price": 2.20},
    ]

    result = base_and_current_price(snapshots, as_of_date="2026-07-02", price_field="price")

    assert result == (2.00, 2.20)


def test_base_and_current_price_base_is_own_first_date_even_out_of_order():
    snapshots = [
        {"scrape_date": "2026-07-03", "price": 2.10, "regular_price": 2.10},
        {"scrape_date": "2026-07-01", "price": 2.00, "regular_price": 2.00},
    ]

    result = base_and_current_price(snapshots, as_of_date="2026-07-03", price_field="price")

    assert result == (2.00, 2.10)


def test_base_and_current_price_returns_none_when_no_snapshots():
    assert base_and_current_price([], as_of_date="2026-07-02", price_field="price") is None


def test_base_and_current_price_returns_none_when_as_of_date_missing():
    snapshots = [{"scrape_date": "2026-07-01", "price": 2.00, "regular_price": 2.00}]

    assert base_and_current_price(snapshots, as_of_date="2026-07-02", price_field="price") is None


def test_class_relatives_groups_by_category_and_computes_relatives():
    basket_rows = [
        _basket_row(1, within_cat_weight=1.0),
        _basket_row(2, within_cat_weight=2.0),
    ]
    snapshots_by_listing = {
        1: [
            {"scrape_date": "2026-07-01", "price": 1.00, "regular_price": 1.00},
            {"scrape_date": "2026-07-02", "price": 1.10, "regular_price": 1.10},
        ],
        2: [
            {"scrape_date": "2026-07-01", "price": 2.00, "regular_price": 2.00},
            {"scrape_date": "2026-07-02", "price": 2.20, "regular_price": 2.20},
        ],
    }

    by_category, n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date="2026-07-02", price_field="price"
    )

    assert n_covered == 2
    assert by_category["01.1.1.1"] == [
        (pytest.approx(1.10), 1.0),
        (pytest.approx(1.10), 2.0),
    ]


def test_class_relatives_skips_listings_missing_todays_snapshot():
    basket_rows = [_basket_row(1)]
    snapshots_by_listing = {1: [{"scrape_date": "2026-07-01", "price": 1.00, "regular_price": 1.00}]}

    by_category, n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date="2026-07-02", price_field="price"
    )

    assert n_covered == 0
    assert by_category == {}


def test_class_relatives_skips_listings_with_zero_base_price():
    basket_rows = [_basket_row(1)]
    snapshots_by_listing = {
        1: [
            {"scrape_date": "2026-07-01", "price": 0, "regular_price": 0},
            {"scrape_date": "2026-07-02", "price": 1.10, "regular_price": 1.10},
        ]
    }

    by_category, n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date="2026-07-02", price_field="price"
    )

    assert n_covered == 0
    assert by_category == {}


def test_class_relatives_defaults_within_cat_weight_when_falsy():
    basket_rows = [_basket_row(1, within_cat_weight=None)]
    snapshots_by_listing = {
        1: [
            {"scrape_date": "2026-07-01", "price": 1.00, "regular_price": 1.00},
            {"scrape_date": "2026-07-02", "price": 1.10, "regular_price": 1.10},
        ]
    }

    by_category, n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date="2026-07-02", price_field="price"
    )

    assert by_category["01.1.1.1"] == [(pytest.approx(1.10), 1.0)]


def test_class_relatives_uses_effective_price_field_when_requested():
    basket_rows = [_basket_row(1)]
    snapshots_by_listing = {
        1: [
            {"scrape_date": "2026-07-01", "price": 0.90, "regular_price": 1.00},
            {"scrape_date": "2026-07-02", "price": 0.80, "regular_price": 1.00},
        ]
    }

    by_category, _ = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date="2026-07-02", price_field="regular_price"
    )

    # regular_price never moved (1.00 -> 1.00) even though effective price did.
    assert by_category["01.1.1.1"] == [(pytest.approx(1.0), 1.0)]


def test_fetch_basket_rows_scopes_to_given_store_ids():
    # This is the actual fix for the cross-country data-corruption bug: a
    # second country's stores must never leak into the first country's
    # 'overall'/'category' aggregation just because both share a COICOP
    # taxonomy. fetch_basket_rows only ever accepts an explicit store_ids
    # list now — there's no more unscoped "every store" code path at all.
    client = FakeSupabaseClient()
    client.table("product_listings").select_results.append([{"id": 1, "store_id": 5}])

    result = fetch_basket_rows(client, [5])

    assert result == [{"id": 1, "store_id": 5}]
    call = client.tables["product_listings"].calls[0]
    assert ("in", "store_id", [5]) in call.filters


def test_fetch_basket_rows_returns_empty_without_querying_when_no_store_ids():
    client = FakeSupabaseClient()

    result = fetch_basket_rows(client, [])

    assert result == []
    assert client.tables == {}  # never even touched product_listings


def test_fetch_category_weights_keyed_by_code_scoped_to_country():
    client = FakeSupabaseClient()
    client.table("category_weights").select_results.append(
        [
            {"ecoicop2_code": "01.1.1.3", "hicp_weight": 17.7},
            {"ecoicop2_code": "01.1.4.1", "hicp_weight": None},  # never fetched yet, no weight
        ]
    )

    weights = fetch_category_weights(client, "PT")

    assert weights == {"01.1.1.3": 17.7}
    call = client.tables["category_weights"].calls[0]
    assert ("eq", "country", "PT") in call.filters


def test_write_index_and_rates_computes_ma7_and_inflation_rate_only_where_history_exists():
    client = FakeSupabaseClient()
    table = client.table("inflation_metrics")
    # Order matches the code's exact query sequence: recent-daily-history once,
    # then one existing-index-at-lookback lookup per period (daily, weekly,
    # monthly, yearly, in that order).
    table.select_results = [
        [{"index_value": 98.0}, {"index_value": 100.0}],  # recent daily history
        [{"index_value": 100.0}],  # existing index at t-1 (daily)
        [],  # existing index at t-7 (weekly) — no history yet
        [],  # existing index at t-30 (monthly)
        [],  # existing index at t-365 (yearly)
    ]

    written = _write_index_and_rates(
        client,
        as_of_date="2026-07-10",
        dimension="category",
        dimension_value="01.1.1.1",
        price_basis="headline",
        index_value=102.0,
        n_products=4,
        coverage=1.0,
        country="PT",
    )

    assert [row["period"] for row in written] == ["daily", "weekly", "monthly", "yearly"]
    daily, weekly, monthly, yearly = written

    assert daily["index_value_ma7"] == pytest.approx(100.0)
    assert daily["inflation_rate"] == pytest.approx(2.0)
    assert weekly["index_value_ma7"] is None
    assert weekly["inflation_rate"] is None
    assert monthly["inflation_rate"] is None
    assert yearly["inflation_rate"] is None

    upserts = [c for c in table.calls if c.op == "upsert"]
    assert len(upserts) == 4
    assert all(c.payload["index_family"] == "fixed_basket" for c in upserts)
    assert all(c.payload["dimension"] == "category" for c in upserts)
    assert all(c.payload["dimension_value"] == "01.1.1.1" for c in upserts)
    assert all(c.payload["price_basis"] == "headline" for c in upserts)
    assert all(c.payload["index_value"] == pytest.approx(102.0) for c in upserts)
    assert all(c.payload["coverage"] == pytest.approx(1.0) for c in upserts)
    assert all(c.payload["country"] == "PT" for c in upserts)
