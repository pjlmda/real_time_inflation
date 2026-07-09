import pytest

from scraper.auchan_france import parse_price_per_unit
from scraper.models import FetchFailed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,63€ / l", (1.63, "EUR/L")),
        ("1,63€ / L", (1.63, "EUR/L")),
        ("4,20€ / kg", (4.20, "EUR/kg")),
        ("0,97€ / u", (0.97, "EUR/un")),
        ("0,29€ / pce", (0.29, "EUR/un")),  # "pce" (pièce) is what auchan.fr actually renders
        ("1€ / l", (1.0, "EUR/L")),  # whole numbers render with no decimal point
    ],
)
def test_parse_price_per_unit_matches_real_auchan_france_formats(text, expected):
    assert parse_price_per_unit(text) == expected


def test_parse_price_per_unit_raises_on_unparseable_text():
    with pytest.raises(FetchFailed):
        parse_price_per_unit("indisponible")
