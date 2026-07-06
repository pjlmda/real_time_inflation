import pytest

from metrics.category_compute import group_by_pair, relative_for_pair


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
