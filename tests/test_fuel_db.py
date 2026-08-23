from fuel.db import upsert_fuel_price
from tests.fake_supabase import FakeSupabaseClient


def test_upsert_fuel_price_writes_country_and_region():
    client = FakeSupabaseClient()
    row = {"date": "2026-07-08", "price": 1.679, "unit": "EUR/L"}

    upsert_fuel_price(client, "gasoline_95", row, country="PT", source="dgeg_national_average")

    call = client.tables["fuel_prices"].calls[0]
    assert call.op == "upsert"
    assert call.payload["fuel_type"] == "gasoline_95"
    assert call.payload["scrape_date"] == "2026-07-08"
    assert call.payload["price"] == 1.679
    assert call.payload["unit"] == "EUR/L"
    assert call.payload["country"] == "PT"
    assert call.payload["region"] == "NATIONAL"
    assert call.payload["source"] == "dgeg_national_average"
    assert call.payload["raw_payload"] == row


def test_upsert_fuel_price_defaults_region_to_national():
    client = FakeSupabaseClient()
    row = {"date": "2026-08-17", "price": 4.099, "unit": "USD/gal"}

    upsert_fuel_price(client, "gasoline_regular", row, country="US", source="eia_weekly_retail")

    call = client.tables["fuel_prices"].calls[0]
    assert call.payload["region"] == "NATIONAL"


def test_upsert_fuel_price_accepts_explicit_padd_region():
    client = FakeSupabaseClient()
    row = {"date": "2026-08-17", "price": 4.210, "unit": "USD/gal"}

    upsert_fuel_price(client, "gasoline_regular", row, country="US", source="eia_weekly_retail", region="PADD1")

    call = client.tables["fuel_prices"].calls[0]
    assert call.payload["region"] == "PADD1"


def test_upsert_fuel_price_passes_through_unit_unchanged():
    # Real bug this guards: the previous version hardcoded an "EUR/"
    # prefix inside db.py regardless of source, which would have
    # mislabeled every US (USD) row's unit as EUR.
    client = FakeSupabaseClient()
    row = {"date": "2026-08-17", "price": 4.099, "unit": "USD/gal"}

    upsert_fuel_price(client, "gasoline_regular", row, country="US", source="eia_weekly_retail")

    call = client.tables["fuel_prices"].calls[0]
    assert call.payload["unit"] == "USD/gal"


def test_upsert_fuel_price_on_conflict_target_includes_country_and_region():
    client = FakeSupabaseClient()
    row = {"date": "2026-07-08", "price": 1.679, "unit": "EUR/L"}

    upsert_fuel_price(client, "gasoline_95", row, country="PT", source="dgeg_national_average")

    call = client.tables["fuel_prices"].calls[0]
    assert call.on_conflict == "fuel_type,scrape_date,country,region"
