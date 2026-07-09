from fuel.db import upsert_fuel_price
from tests.fake_supabase import FakeSupabaseClient


def test_upsert_fuel_price_maps_known_unit_abbreviation():
    client = FakeSupabaseClient()
    row = {"date": "2026-07-08", "price": 1.679, "unit": "litro"}

    upsert_fuel_price(client, "gasoline_95", row)

    call = client.tables["fuel_prices"].calls[0]
    assert call.op == "upsert"
    assert call.payload["fuel_type"] == "gasoline_95"
    assert call.payload["scrape_date"] == "2026-07-08"
    assert call.payload["price"] == 1.679
    assert call.payload["unit"] == "EUR/L"
    assert call.payload["source"] == "dgeg_national_average"
    assert call.payload["raw_payload"] == row


def test_upsert_fuel_price_passes_through_unrecognized_unit():
    client = FakeSupabaseClient()
    row = {"date": "2026-07-08", "price": 0.75, "unit": "gallon"}

    upsert_fuel_price(client, "lpg_auto", row)

    call = client.tables["fuel_prices"].calls[0]
    assert call.payload["unit"] == "EUR/gallon"


def test_upsert_fuel_price_unit_lookup_is_case_insensitive():
    client = FakeSupabaseClient()
    row = {"date": "2026-07-08", "price": 1.5, "unit": "KG"}

    upsert_fuel_price(client, "lpg_auto", row)

    call = client.tables["fuel_prices"].calls[0]
    assert call.payload["unit"] == "EUR/kg"
