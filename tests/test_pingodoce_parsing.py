import pytest

from scraper.pingodoce import _parse_unit_measure


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
    assert _parse_unit_measure(text, fallback_price=999) == expected


def test_parse_unit_measure_falls_back_when_unparseable():
    assert _parse_unit_measure("", fallback_price=1.23) == (1.23, "EUR/unit")
    assert _parse_unit_measure("indisponível", fallback_price=1.23) == (1.23, "EUR/unit")
