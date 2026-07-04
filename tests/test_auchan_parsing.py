import pytest

from scraper.auchan import parse_price_per_unit
from scraper.models import FetchFailed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0.86 €/Lt", (0.86, "EUR/L")),
        ("1.63 €/Kg", (1.63, "EUR/kg")),
        ("0.24 €/un", (0.24, "EUR/un")),
        ("4.14 €/Kg", (4.14, "EUR/kg")),
        ("1 €/Lt", (1.0, "EUR/L")),  # whole numbers render with no decimal point
    ],
)
def test_parse_price_per_unit_matches_real_auchan_formats(text, expected):
    assert parse_price_per_unit(text) == expected


def test_parse_price_per_unit_raises_on_unparseable_text():
    with pytest.raises(FetchFailed):
        parse_price_per_unit("indisponível")
