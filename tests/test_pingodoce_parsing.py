import pytest

from scraper.pingodoce import parse_unit_measure


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1 L | 0,9 €/L", (0.9, "EUR/L")),
        ("0.5 Kg | 2,52 €/Kg", (2.52, "EUR/kg")),
        ("12 Un | 0,26 €/Un", (0.26, "EUR/un")),
        ("3 L | 4,98 €/L", (4.98, "EUR/L")),
        ("0.45 Kg | 2,87 €/Kg", (2.87, "EUR/kg")),
    ],
)
def test_parse_unit_measure_matches_real_pingodoce_formats(text, expected):
    assert parse_unit_measure(text, fallback_price=999) == expected


def test_parse_unit_measure_falls_back_when_unparseable():
    assert parse_unit_measure("", fallback_price=1.23) == (1.23, "EUR/unit")
    assert parse_unit_measure("indisponível", fallback_price=1.23) == (1.23, "EUR/unit")


def test_parse_unit_measure_computes_price_per_unit_for_weight_only_text():
    # Fresh/weight-sold items (talho, charcutaria) show only a weight, no
    # embedded price-per-unit — must be computed from the sales price.
    assert parse_unit_measure("1.5 Kg", fallback_price=2.49) == (pytest.approx(1.66), "EUR/kg")
