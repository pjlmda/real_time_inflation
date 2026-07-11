import json
from pathlib import Path

import httpx
import pytest

from tests.fake_supabase import FakeSupabaseClient
from weights.bls import SOURCE_DATASET, BlsRequestFailed, fetch_weights, parse_response
from weights.eurostat import upsert_weights

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture():
    return json.loads((FIXTURES / "bls_cpi_relative_importance_sample.json").read_text(encoding="utf-8"))


def test_parse_response_uses_latest_period_and_converts_percent_to_permille():
    records = parse_response(_load_fixture())

    bread = next(r for r in records if r.ecoicop2_code == "01.1.1.3")
    # BLS Relative Importance is a 0-100 percentage (0.173); this project's
    # hicp_weight convention (matching Eurostat's existing PT/FR rows) is
    # per-mille (0-1000) - 0.173 * 10 = 1.73, not the raw 0.173 or 0.171
    # (the "previous year" aspect, which must not be picked instead).
    assert bread.weight == 1.73
    assert bread.weight_year == 2026


def test_parse_response_maps_one_bls_item_to_both_rice_and_pasta():
    # SEFA03 ("Rice, pasta, cornmeal") is BLS's own single item covering
    # both ECOICOP classes - a disclosed granularity gap, not a bug.
    records = parse_response(_load_fixture())

    by_code = {r.ecoicop2_code: r.weight for r in records}
    assert by_code["01.1.1.1"] == by_code["01.1.1.6"]
    assert round(by_code["01.1.1.1"], 4) == 1.4


def test_parse_response_skips_series_with_no_data():
    records = parse_response(_load_fixture())

    # CUUR0000SEFZZ has an empty "data" list in the fixture (simulating a
    # rate-limited or nonexistent series) - must be skipped, not crash or
    # produce a bogus zero-weight record.
    assert all(r.ecoicop2_code not in ("SEFZZ",) for r in records)
    assert len(records) == 3  # bread + rice + pasta, nothing from SEFZZ


def test_upsert_weights_records_bls_source_dataset_not_eurostats():
    # Real bug this guards: upsert_weights() used to hardcode Eurostat's own
    # SOURCE_DATASET constant regardless of caller, which would have
    # mislabeled every BLS-sourced hicp_weights_cache row as 'prc_hicp_inw'.
    client = FakeSupabaseClient()
    client.table("categories").select_results.append([{"ecoicop2_code": "01.1.1.3"}])
    records = parse_response(_load_fixture())
    bread_only = [r for r in records if r.ecoicop2_code == "01.1.1.3"]

    upsert_weights(bread_only, client, country="US", source_dataset=SOURCE_DATASET)

    cache_call = client.tables["hicp_weights_cache"].calls[0]
    assert cache_call.payload[0]["source_dataset"] == "bls_cpi_relative_importance"
    assert cache_call.payload[0]["country"] == "US"


def test_fetch_weights_raises_on_declined_request_instead_of_silent_empty_result(monkeypatch):
    # Real bug this guards: confirmed live 2026-07-11 - hitting the API's
    # daily unauthenticated-request quota returns a 200 OK with no "Results"
    # key at all, which parse_response() alone would silently treat as "zero
    # series had data" - main() then reported "Synced 0 weight records" with
    # no indication anything had actually failed. A rate-limited (or
    # otherwise declined) request must raise, not silently succeed empty.
    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", args[0] if args else kwargs.get("url", "https://api.bls.gov/x"))
        return httpx.Response(
            200,
            json={
                "status": "REQUEST_NOT_PROCESSED",
                "message": ["Request could not be serviced, as the daily threshold ... has been reached."],
            },
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(BlsRequestFailed):
        fetch_weights()
