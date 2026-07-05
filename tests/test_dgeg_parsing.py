from pathlib import Path

from fuel.dgeg import parse_price_table

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_price_table_extracts_rows_most_recent_first():
    html = (FIXTURES / "dgeg_price_table.html").read_text(encoding="utf-8")

    rows = parse_price_table(html)

    assert len(rows) == 2
    assert rows[0] == {
        "date": "2026-07-04",
        "fuel_name": "Gasolina simples 95",
        "price": 1.873,
        "unit": "litro",
        "n_stations": 1650,
    }
    assert rows[1]["date"] == "2026-07-03"
    assert rows[1]["price"] == 1.877


def test_parse_price_table_returns_empty_list_when_no_rows():
    assert parse_price_table("<html><body>no data</body></html>") == []
