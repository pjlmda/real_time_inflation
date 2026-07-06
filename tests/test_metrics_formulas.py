import math

import pytest

from metrics.formulas import (
    inflation_rate,
    jevons_class_index,
    moving_average,
    weighted_overall_index,
)


def test_jevons_class_index_equal_weights_is_plain_geometric_mean():
    # sqrt(1.10 * 1.00) * 100
    result = jevons_class_index([(1.10, 0.5), (1.00, 0.5)])
    assert result == pytest.approx(math.sqrt(1.10) * 100, rel=1e-9)


def test_jevons_class_index_unequal_weights():
    # 1.20^0.75 * 1.00^0.25 * 100
    result = jevons_class_index([(1.20, 0.75), (1.00, 0.25)])
    assert result == pytest.approx((1.20 ** 0.75) * 100, rel=1e-9)


def test_jevons_class_index_normalizes_unnormalized_weights():
    # weights [3, 1] (sum 4) should give the same result as [0.75, 0.25]
    unnormalized = jevons_class_index([(1.20, 3), (1.00, 1)])
    normalized = jevons_class_index([(1.20, 0.75), (1.00, 0.25)])
    assert unnormalized == pytest.approx(normalized, rel=1e-9)


def test_jevons_class_index_no_change_is_100():
    assert jevons_class_index([(1.0, 1.0), (1.0, 2.0)]) == pytest.approx(100.0)


def test_jevons_class_index_rejects_zero_total_weight():
    with pytest.raises(ValueError):
        jevons_class_index([(1.1, 0.0)])


def test_weighted_overall_index_matches_hand_computed_value():
    # (110*0.6 + 100*0.4) / 1.0 = 106.0
    result = weighted_overall_index([(110.0, 0.6), (100.0, 0.4)])
    assert result == pytest.approx(106.0)


def test_weighted_overall_index_normalizes_unnormalized_weights():
    unnormalized = weighted_overall_index([(110.0, 6), (100.0, 4)])
    assert unnormalized == pytest.approx(106.0)


def test_inflation_rate_positive_and_negative():
    assert inflation_rate(105.0, 100.0) == pytest.approx(5.0)
    assert inflation_rate(95.0, 100.0) == pytest.approx(-5.0)
    assert inflation_rate(100.0, 100.0) == pytest.approx(0.0)


def test_inflation_rate_rejects_zero_base():
    with pytest.raises(ValueError):
        inflation_rate(100.0, 0.0)


def test_moving_average_of_single_value_is_itself():
    assert moving_average([100.0]) == pytest.approx(100.0)


def test_moving_average_matches_hand_computed_value():
    assert moving_average([98.0, 100.0, 102.0]) == pytest.approx(100.0)


def test_moving_average_rejects_empty_list():
    with pytest.raises(ValueError):
        moving_average([])
