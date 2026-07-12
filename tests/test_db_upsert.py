from scraper.db import scrape_date_for_timezone, SupabaseWriter
from scraper.models import RunResult, ScrapedPrice
from tests.fake_supabase import FakeSupabaseClient


def make_writer(timezone_id="Europe/Lisbon", currency="EUR"):
    client = FakeSupabaseClient()
    return SupabaseWriter(client, timezone_id=timezone_id, currency=currency), client


def test_upsert_snapshot_sends_correct_row_and_conflict_key():
    writer, client = make_writer()
    scraped = ScrapedPrice(
        price=0.79,
        regular_price=0.89,
        price_per_unit=0.79,
        unit_basis="EUR/L",
        is_promotion=True,
        promotion_label="-10%",
        in_stock=True,
        raw_payload={"source": "json-ld"},
    )

    writer.upsert_snapshot(listing_id=42, scraped=scraped)

    calls = client.tables["price_snapshots"].calls
    assert len(calls) == 1
    call = calls[0]
    assert call.op == "upsert"
    assert call.payload["listing_id"] == 42
    assert call.payload["scrape_date"] == scrape_date_for_timezone("Europe/Lisbon")
    assert call.payload["price"] == 0.79
    assert call.payload["is_promotion"] is True
    assert call.payload["currency"] == "EUR"


def test_upsert_snapshot_uses_the_writers_own_configured_timezone():
    # The actual bug this generalizes away: scrape_date used to be pinned to
    # a single global Europe/Lisbon constant regardless of which store's
    # writer was doing the writing. A French store's writer must use its own
    # timezone (Europe/Paris is a full hour ahead of Lisbon year-round, not
    # a DST-only difference) rather than silently inheriting Portugal's.
    writer, client = make_writer(timezone_id="Europe/Paris")
    scraped = ScrapedPrice(
        price=1.0,
        regular_price=1.0,
        price_per_unit=1.0,
        unit_basis="EUR/kg",
        is_promotion=False,
        promotion_label=None,
        in_stock=True,
        raw_payload={},
    )

    writer.upsert_snapshot(listing_id=1, scraped=scraped)

    call = client.tables["price_snapshots"].calls[0]
    assert call.payload["scrape_date"] == scrape_date_for_timezone("Europe/Paris")


def test_upsert_snapshot_uses_the_writers_own_configured_currency():
    # The bug this generalizes away: currency used to be hardcoded 'EUR' in
    # upsert_snapshot regardless of which store's writer was doing the
    # writing, never caught because every store built before Wegmans (USD)
    # was EUR-denominated - a US store's writer must use its own currency
    # rather than silently mislabeling every price_snapshots row as EUR.
    writer, client = make_writer(currency="USD")
    scraped = ScrapedPrice(
        price=2.99,
        regular_price=2.99,
        price_per_unit=2.99,
        unit_basis="USD/gallon",
        is_promotion=False,
        promotion_label=None,
        in_stock=True,
        raw_payload={},
    )

    writer.upsert_snapshot(listing_id=1, scraped=scraped)

    call = client.tables["price_snapshots"].calls[0]
    assert call.payload["currency"] == "USD"


def test_get_captured_today_listing_ids_returns_set_of_captured_ids():
    writer, client = make_writer()
    client.table("price_snapshots").select_results.append([{"listing_id": 42}, {"listing_id": 7}])

    result = writer.get_captured_today_listing_ids([42, 7, 99])

    assert result == {42, 7}
    call = client.tables["price_snapshots"].calls[0]
    assert ("in", "listing_id", [42, 7, 99]) in call.filters
    assert ("eq", "scrape_date", scrape_date_for_timezone("Europe/Lisbon")) in call.filters


def test_get_captured_today_listing_ids_returns_empty_without_querying_when_no_ids():
    writer, client = make_writer()

    result = writer.get_captured_today_listing_ids([])

    assert result == set()
    assert client.tables == {}  # never even touched price_snapshots


def test_get_category_ids_keyed_by_ecoicop2_code():
    writer, client = make_writer()
    client.table("categories").select_results.append(
        [{"id": 3, "ecoicop2_code": "01.1.1.1"}, {"id": 8, "ecoicop2_code": "01.1.1.3"}]
    )

    result = writer.get_category_ids(["01.1.1.1", "01.1.1.3"])

    assert result == {"01.1.1.1": 3, "01.1.1.3": 8}
    call = client.tables["categories"].calls[0]
    assert ("in", "ecoicop2_code", ["01.1.1.1", "01.1.1.3"]) in call.filters


def test_get_captured_today_category_ids_returns_set_scoped_to_store():
    writer, client = make_writer()
    client.table("category_observations").select_results.append(
        [{"category_id": 3}, {"category_id": 8}]
    )

    result = writer.get_captured_today_category_ids(store_id=5, category_ids=[3, 8, 12])

    assert result == {3, 8}
    call = client.tables["category_observations"].calls[0]
    assert ("eq", "store_id", 5) in call.filters
    assert ("in", "category_id", [3, 8, 12]) in call.filters


def test_finish_run_sends_status_and_coverage():
    writer, client = make_writer()
    result = RunResult(
        run_id=7,
        attempted=10,
        ok=8,
        failed=2,
        status="partial",
        coverage=0.8,
        error_summary="listing 3: timeout",
    )

    writer.finish_run(result)

    call = client.tables["scrape_runs"].calls[0]
    assert call.op == "update"
    assert call.payload["status"] == "partial"
    assert call.payload["coverage"] == 0.8
    assert call.payload["listings_ok"] == 8


def test_mark_alerted_sets_flag_true():
    writer, client = make_writer()

    writer.mark_alerted(run_id=7)

    call = client.tables["scrape_runs"].calls[0]
    assert call.payload == {"alerted": True}
