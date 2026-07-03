import json
from pathlib import Path

import pytest

from scraper.continente import _parse_price, _parse_price_per_unit, parse_json_ld
from scraper.models import FetchFailed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_json_ld_extracts_price_from_product_offer():
    raw = (FIXTURES / "continente_product_sample.json").read_text(encoding="utf-8")
    json.loads(raw)  # sanity: fixture itself is valid JSON

    result = parse_json_ld([raw])

    assert result is not None
    assert result.price == 0.79
    assert result.in_stock is True
    assert result.raw_payload["source"] == "json-ld"


def test_parse_json_ld_returns_none_when_no_product_block():
    result = parse_json_ld(["{}", "not json"])
    assert result is None


def test_parse_price_handles_comma_decimal_and_currency_symbol():
    assert _parse_price("0,86€") == 0.86
    assert _parse_price("4\n,09€") == 4.09


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0,86€/lt", (0.86, "EUR/L")),
        ("5,45€/lt", (5.45, "EUR/L")),
        ("1,82€/kg", (1.82, "EUR/kg")),
        ("3,09€/doz", (3.09, "EUR/doz")),
    ],
)
def test_parse_price_per_unit_matches_real_continente_formats(text, expected):
    assert _parse_price_per_unit(text) == expected


def test_parse_price_per_unit_raises_on_unparseable_text():
    with pytest.raises(FetchFailed):
        _parse_price_per_unit("indisponível")
