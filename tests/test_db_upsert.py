from scraper.db import lisbon_scrape_date, SupabaseWriter
from scraper.models import RunResult, ScrapedPrice
from tests.fake_supabase import FakeSupabaseClient


def make_writer():
    client = FakeSupabaseClient()
    return SupabaseWriter(client), client


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
    assert call.payload["scrape_date"] == lisbon_scrape_date()
    assert call.payload["price"] == 0.79
    assert call.payload["is_promotion"] is True
    assert call.payload["currency"] == "EUR"


def test_listing_already_captured_today_true_when_row_exists():
    writer, client = make_writer()
    client.table("price_snapshots").select_results.append([{"id": 1}])

    assert writer.listing_already_captured_today(listing_id=42) is True


def test_listing_already_captured_today_false_when_no_rows():
    writer, client = make_writer()
    client.table("price_snapshots").select_results.append([])

    assert writer.listing_already_captured_today(listing_id=42) is False


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
