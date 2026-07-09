import pytest

from metrics.category_compute import (
    _write_index_and_rates,
    compute_category_avg_metrics_for_date,
    group_by_pair,
    relative_for_pair,
)
from tests.fake_supabase import FakeSupabaseClient


def test_group_by_pair_groups_rows_by_store_and_category():
    rows = [
        {"store_id": 1, "category_id": 10, "scrape_date": "2026-07-01"},
        {"store_id": 1, "category_id": 10, "scrape_date": "2026-07-02"},
        {"store_id": 2, "category_id": 10, "scrape_date": "2026-07-01"},
    ]

    grouped = group_by_pair(rows)

    assert set(grouped.keys()) == {(1, 10), (2, 10)}
    assert len(grouped[(1, 10)]) == 2
    assert len(grouped[(2, 10)]) == 1


def test_relative_for_pair_uses_first_ever_row_as_base():
    pair_rows = [
        {"scrape_date": "2026-07-01", "median_price_per_unit": 2.00, "n_products": 8},
        {"scrape_date": "2026-07-02", "median_price_per_unit": 2.20, "n_products": 9},
    ]

    result = relative_for_pair(pair_rows, as_of_date="2026-07-02")

    assert result == (pytest.approx(1.10), 9)


def test_relative_for_pair_base_is_own_first_date_even_out_of_order():
    pair_rows = [
        {"scrape_date": "2026-07-03", "median_price_per_unit": 2.10, "n_products": 5},
        {"scrape_date": "2026-07-01", "median_price_per_unit": 2.00, "n_products": 8},
    ]

    result = relative_for_pair(pair_rows, as_of_date="2026-07-03")

    assert result == (pytest.approx(1.05), 5)


def test_relative_for_pair_returns_none_when_as_of_date_missing():
    pair_rows = [{"scrape_date": "2026-07-01", "median_price_per_unit": 2.00, "n_products": 8}]

    assert relative_for_pair(pair_rows, as_of_date="2026-07-02") is None


def test_relative_for_pair_returns_none_when_base_is_zero():
    pair_rows = [
        {"scrape_date": "2026-07-01", "median_price_per_unit": 0, "n_products": 8},
        {"scrape_date": "2026-07-02", "median_price_per_unit": 2.20, "n_products": 9},
    ]

    assert relative_for_pair(pair_rows, as_of_date="2026-07-02") is None


def test_relative_for_pair_returns_none_when_today_value_missing():
    pair_rows = [
        {"scrape_date": "2026-07-01", "median_price_per_unit": 2.00, "n_products": 8},
        {"scrape_date": "2026-07-02", "median_price_per_unit": None, "n_products": 0},
    ]

    assert relative_for_pair(pair_rows, as_of_date="2026-07-02") is None


def test_compute_category_avg_metrics_for_date_returns_empty_when_no_observations():
    client = FakeSupabaseClient()
    client.table("category_observations").select_results.append([])

    result = compute_category_avg_metrics_for_date(client, as_of_date="2026-07-10")

    assert result == []


def test_write_index_and_rates_computes_ma7_and_inflation_rate_only_where_history_exists():
    client = FakeSupabaseClient()
    table = client.table("inflation_metrics")
    # Same query-order contract as metrics/compute.py's sibling function: one
    # recent-daily-history lookup, then one existing-index lookup per period.
    table.select_results = [
        [{"index_value": 99.0}, {"index_value": 100.0}],  # recent daily history
        [{"index_value": 100.0}],  # existing index at t-1 (daily)
        [],  # existing index at t-7 (weekly)
        [],  # existing index at t-30 (monthly)
        [],  # existing index at t-365 (yearly)
    ]

    written = _write_index_and_rates(
        client,
        as_of_date="2026-07-10",
        dimension="overall",
        dimension_value="ALL",
        index_value=101.0,
        n_products=50,
        coverage=0.9,
    )

    assert [row["period"] for row in written] == ["daily", "weekly", "monthly", "yearly"]
    daily, weekly, monthly, yearly = written

    assert daily["index_value_ma7"] == pytest.approx(100.0)
    assert daily["inflation_rate"] == pytest.approx(1.0)
    assert weekly["inflation_rate"] is None
    assert monthly["inflation_rate"] is None
    assert yearly["inflation_rate"] is None

    upserts = [c for c in table.calls if c.op == "upsert"]
    assert len(upserts) == 4
    assert all(c.payload["index_family"] == "category_avg" for c in upserts)
    assert all(c.payload["price_basis"] == "effective" for c in upserts)
    assert all(c.payload["dimension"] == "overall" for c in upserts)
    assert all(c.payload["dimension_value"] == "ALL" for c in upserts)
