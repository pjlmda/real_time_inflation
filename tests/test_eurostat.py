import json
from pathlib import Path

from weights.eurostat import parse_response

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_response_returns_only_latest_year():
    raw = json.loads((FIXTURES / "eurostat_prc_hicp_inw_sample.json").read_text(encoding="utf-8"))

    records = parse_response(raw)

    assert {r.weight_year for r in records} == {2024}
    by_code = {r.ecoicop2_code: r.weight for r in records}
    assert by_code["CP01113"] == 13.1
    assert by_code["CP01146"] == 2.3
