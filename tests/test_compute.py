import pytest

from metrics.compute import (
    CORRUPTED_SNAPSHOTS,
    base_and_current_price,
    build_index_rows,
    class_relatives,
    fetch_basket_rows,
    fetch_category_weights,
    fetch_lookback_indices,
    fetch_recent_daily_map,
    fetch_snapshots_by_listing,
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


def test_class_relatives_skips_explicitly_listed_corrupted_snapshots():
    # Regression test for the Lidl France wine bug (scraper/lidl_france.py,
    # fixed 2026-07-23): a page-wide (not tile-scoped) stroke-price locator
    # picked up an unrelated carousel item's price, so listing 815's
    # regular_price on 2026-07-16 is a known-bad scraper-bug artifact, not a
    # real price. It must be excluded from the headline (regular_price)
    # basis for that exact day, while the effective (price) basis for the
    # SAME listing/day - which was never wrong - stays fully covered.
    listing_id, bad_date, bad_field = next(iter(CORRUPTED_SNAPSHOTS))
    basket_rows = [_basket_row(listing_id)]
    snapshots_by_listing = {
        listing_id: [
            {"scrape_date": "2026-07-01", "price": 1.00, "regular_price": 1.00},
            {"scrape_date": bad_date, "price": 1.10, "regular_price": 999.00},
        ]
    }

    excluded_by_category, excluded_n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date=bad_date, price_field=bad_field
    )
    other_field = "price" if bad_field == "regular_price" else "regular_price"
    unaffected_by_category, unaffected_n_covered = class_relatives(
        basket_rows, snapshots_by_listing, as_of_date=bad_date, price_field=other_field
    )

    assert excluded_n_covered == 0
    assert excluded_by_category == {}
    assert unaffected_n_covered == 1


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


def test_fetch_snapshots_by_listing_paginates_past_the_1000_row_page_size():
    # Regression test for the PostgREST-default-1000-row-cap bug class (same
    # class already found and fixed once in web/api/db.py:
    # get_available_countries) - as price_snapshots history grows past 1000
    # rows for a country's listings, a single unpaginated .execute() used to
    # silently truncate, undercounting coverage and dropping whole
    # categories from the dashboard. This asserts fetch_snapshots_by_listing
    # keeps paging (a second .execute() call) until a short page ends it.
    client = FakeSupabaseClient()
    first_page = [{"listing_id": 1, "scrape_date": f"day-{i}", "price": 1.0, "regular_price": 1.0} for i in range(1000)]
    second_page = [{"listing_id": 2, "scrape_date": "2026-07-23", "price": 2.0, "regular_price": 2.0}]
    client.table("price_snapshots").select_results.append(first_page)
    client.table("price_snapshots").select_results.append(second_page)

    result = fetch_snapshots_by_listing(client, [1, 2])

    assert len(client.tables["price_snapshots"].calls) == 2
    assert len(result[1]) == 1000
    assert result[2] == second_page


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


def test_fetch_lookback_indices_maps_rows_to_period_via_target_date():
    # One batched query replaces what used to be one _existing_index query
    # per (scope, period) — each row's period is recovered from which of the
    # 4 lookback target dates (as_of_date minus that period's lookback days)
    # its as_of_date matches.
    client = FakeSupabaseClient()
    client.table("inflation_metrics").select_results.append(
        [
            {
                "as_of_date": "2026-07-09",  # 2026-07-10 minus 1 day -> daily
                "dimension": "category",
                "dimension_value": "01.1.1.1",
                "price_basis": "headline",
                "index_value": 100.0,
            },
            {
                "as_of_date": "2026-07-03",  # minus 7 days -> weekly
                "dimension": "category",
                "dimension_value": "01.1.1.1",
                "price_basis": "headline",
                "index_value": 95.0,
            },
        ]
    )

    lookback = fetch_lookback_indices(client, "2026-07-10", "PT")

    assert lookback[("daily", "category", "01.1.1.1", "headline")] == pytest.approx(100.0)
    assert lookback[("weekly", "category", "01.1.1.1", "headline")] == pytest.approx(95.0)
    call = client.tables["inflation_metrics"].calls[0]
    assert ("eq", "country", "PT") in call.filters
    assert ("eq", "index_family", "fixed_basket") in call.filters
    in_filter = next(f for f in call.filters if f[0] == "in")
    assert set(in_filter[2]) == {"2026-07-09", "2026-07-03", "2026-06-10", "2025-07-10"}


def test_fetch_recent_daily_map_groups_by_scope_key():
    client = FakeSupabaseClient()
    client.table("inflation_metrics").select_results.append(
        [
            {"dimension": "category", "dimension_value": "01.1.1.1", "price_basis": "headline", "index_value": 98.0},
            {"dimension": "category", "dimension_value": "01.1.1.1", "price_basis": "headline", "index_value": 100.0},
        ]
    )

    recent = fetch_recent_daily_map(client, "2026-07-10", "PT")

    assert recent[("category", "01.1.1.1", "headline")] == [98.0, 100.0]
    call = client.tables["inflation_metrics"].calls[0]
    assert ("eq", "period", "daily") in call.filters
    assert ("gte", "as_of_date", "2026-07-04") in call.filters
    assert ("lte", "as_of_date", "2026-07-09") in call.filters


def test_build_index_rows_computes_ma7_and_inflation_rate_only_where_history_exists():
    # No client/DB involved now — build_index_rows is pure, fed by
    # fetch_lookback_indices/fetch_recent_daily_map's precomputed maps.
    lookback = {("daily", "category", "01.1.1.1", "headline"): 100.0}
    recent_daily = {("category", "01.1.1.1", "headline"): [98.0, 100.0]}

    rows = build_index_rows(
        as_of_date="2026-07-10",
        dimension="category",
        dimension_value="01.1.1.1",
        price_basis="headline",
        index_value=102.0,
        n_products=4,
        coverage=1.0,
        country="PT",
        lookback=lookback,
        recent_daily=recent_daily,
    )

    assert [row["period"] for row in rows] == ["daily", "weekly", "monthly", "yearly"]
    daily, weekly, monthly, yearly = rows

    assert daily["index_value_ma7"] == pytest.approx(100.0)
    assert daily["inflation_rate"] == pytest.approx(2.0)
    assert weekly["index_value_ma7"] is None
    assert weekly["inflation_rate"] is None
    assert monthly["inflation_rate"] is None
    assert yearly["inflation_rate"] is None

    assert all(row["index_family"] == "fixed_basket" for row in rows)
    assert all(row["dimension"] == "category" for row in rows)
    assert all(row["dimension_value"] == "01.1.1.1" for row in rows)
    assert all(row["price_basis"] == "headline" for row in rows)
    assert all(row["index_value"] == pytest.approx(102.0) for row in rows)
    assert all(row["coverage"] == pytest.approx(1.0) for row in rows)
    assert all(row["country"] == "PT" for row in rows)
