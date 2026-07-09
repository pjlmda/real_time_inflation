import json
from pathlib import Path

from tests.fake_supabase import FakeSupabaseClient
from weights.eurostat import WeightRecord, parse_response, to_dotted_ecoicop, upsert_weights

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_response_returns_only_latest_year():
    raw = json.loads((FIXTURES / "eurostat_prc_hicp_inw_sample.json").read_text(encoding="utf-8"))

    records = parse_response(raw)

    assert {r.weight_year for r in records} == {2024}
    by_code = {r.ecoicop2_code: r.weight for r in records}
    assert by_code["01.1.1.3"] == 13.1
    assert by_code["01.1.4.6"] == 2.3


def test_to_dotted_ecoicop_converts_eurostat_compact_codes():
    assert to_dotted_ecoicop("CP01113") == "01.1.1.3"
    assert to_dotted_ecoicop("CP0114") == "01.1.4"
    assert to_dotted_ecoicop("CP01146") == "01.1.4.6"
    assert to_dotted_ecoicop("CP01116") == "01.1.1.6"
    assert to_dotted_ecoicop("CP01153") == "01.1.5.3"


def test_to_dotted_ecoicop_passes_through_non_numeric_aggregates():
    assert to_dotted_ecoicop("TOT_X_TBC") == "TOT_X_TBC"
    assert to_dotted_ecoicop("CP00") == "00"


def test_upsert_weights_writes_country_scoped_cache_and_category_rows():
    client = FakeSupabaseClient()
    client.table("categories").select_results.append([{"ecoicop2_code": "01.1.1.3"}])
    records = [WeightRecord(ecoicop2_code="01.1.1.3", weight_year=2026, weight=17.7)]

    upsert_weights(records, client, country="FR")

    cache_call = client.tables["hicp_weights_cache"].calls[0]
    assert cache_call.op == "insert"
    assert cache_call.payload[0]["country"] == "FR"
    assert cache_call.payload[0]["ecoicop2_code"] == "01.1.1.3"

    weight_call = client.tables["category_weights"].calls[0]
    assert weight_call.op == "upsert"
    assert weight_call.payload == {
        "ecoicop2_code": "01.1.1.3",
        "country": "FR",
        "hicp_weight": 17.7,
        "weight_year": 2026,
    }


def test_upsert_weights_skips_codes_not_yet_seeded():
    client = FakeSupabaseClient()
    client.table("categories").select_results.append([])  # nothing seeded yet
    records = [WeightRecord(ecoicop2_code="99.9.9.9", weight_year=2026, weight=1.0)]

    upsert_weights(records, client, country="FR")

    assert "category_weights" not in client.tables
