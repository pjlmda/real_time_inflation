import json
from pathlib import Path

import httpx
import pytest

from fuel.eia import EiaRequestFailed, fetch_all_latest_prices, parse_response

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture():
    return json.loads((FIXTURES / "eia_gnd_sample.json").read_text(encoding="utf-8"))


def test_parse_response_extracts_national_and_padd_rows():
    rows = parse_response(_load_fixture(), "gasoline_regular")

    by_region = {r["region"]: r for r in rows}
    assert by_region["NATIONAL"]["price"] == 4.099
    assert by_region["PADD1"]["price"] == 4.210
    assert by_region["PADD3"]["price"] == 3.782
    assert all(r["fuel_type"] == "gasoline_regular" for r in rows)


def test_parse_response_converts_dollar_per_gallon_units():
    rows = parse_response(_load_fixture(), "gasoline_regular")

    assert all(r["unit"] == "USD/gal" for r in rows)


def test_parse_response_skips_unrecognized_duoarea_codes():
    # R1Y (PADD 1B, a subregion) isn't in PADD_REGIONS - must be dropped,
    # not guessed at or mislabeled as one of the 5 tracked PADD regions.
    rows = parse_response(_load_fixture(), "gasoline_regular")

    assert all(r["region"] != "R1Y" for r in rows)
    assert len(rows) == 3  # NATIONAL, PADD1, PADD3 - not R1Y, not the older NUS row


def test_parse_response_keeps_only_latest_period_per_duoarea():
    # The fixture has two NUS rows (2026-08-17 and 2026-08-10, desc-sorted)
    # - only the most recent should survive.
    rows = parse_response(_load_fixture(), "gasoline_regular")

    national_rows = [r for r in rows if r["region"] == "NATIONAL"]
    assert len(national_rows) == 1
    assert national_rows[0]["date"] == "2026-08-17"


def test_fetch_all_latest_prices_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)

    with pytest.raises(EiaRequestFailed):
        fetch_all_latest_prices()


def test_fetch_all_latest_prices_raises_on_api_error_response(monkeypatch):
    # Real-shape guard, mirroring weights.bls's
    # test_fetch_weights_raises_on_declined_request...: an API-level
    # decline (bad key, invalid facet) must raise, not be silently parsed
    # as "zero rows today".
    monkeypatch.setenv("EIA_API_KEY", "fake-key-for-test")

    def fake_get(*args, **kwargs):
        request = httpx.Request("GET", args[0] if args else kwargs.get("url", "https://api.eia.gov/x"))
        return httpx.Response(200, json={"error": "invalid api_key"}, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(EiaRequestFailed):
        fetch_all_latest_prices()
