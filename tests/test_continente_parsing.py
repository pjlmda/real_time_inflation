import json
from pathlib import Path

from scraper.continente import parse_json_ld

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
