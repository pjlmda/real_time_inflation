from datetime import datetime, timezone

import pytest

import scraper.base as base_module
from scraper.base import BaseScraper
from scraper.models import FetchFailed, Listing, ScrapedPrice
from scraper.store_config import StoreConfig


def _make_config():
    return StoreConfig(
        slug="test-store",
        name="Test Store",
        base_url="https://example.com",
        user_agent="test-agent",
        delay_seconds_min=1,
        delay_seconds_max=2,
        locale="pt-PT",
        timezone_id="Europe/Lisbon",
    )


def _make_listing(listing_id):
    return Listing(id=listing_id, product_id=listing_id, store_id=1, url=f"https://example.com/{listing_id}", store_sku=None)


class _FakeRobots:
    def __init__(self, disallowed_ids: frozenset = frozenset()):
        self._disallowed_ids = disallowed_ids

    def allowed(self, url: str) -> bool:
        return not any(url.endswith(f"/{lid}") for lid in self._disallowed_ids)

    def crawl_delay(self):
        return None


class _FakeContext:
    async def new_page(self):
        return object()

    async def close(self):
        pass


class _FakeAsyncPlaywrightCM:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


class _FakeDb:
    def __init__(
        self,
        listings,
        already_captured_ids=frozenset(),
        latest_run=None,
        start_run_error: Exception | None = None,
        finish_run_error: Exception | None = None,
        mark_alerted_error: Exception | None = None,
    ):
        self._listings = listings
        self._already_captured_ids = already_captured_ids
        self._latest_run = latest_run
        self._start_run_error = start_run_error
        self._finish_run_error = finish_run_error
        self._mark_alerted_error = mark_alerted_error
        self.finished = None
        self.alerted_run_id = None
        self.upserted: list[tuple[int, ScrapedPrice]] = []

    def get_store_id(self, slug):
        return 1

    def get_latest_run(self, store_id, mode):
        return self._latest_run

    def update_robots_checked(self, store_id):
        pass

    def get_active_listings(self, store_id):
        return self._listings

    def listing_already_captured_today(self, listing_id):
        return listing_id in self._already_captured_ids

    def start_run(self, store_id, mode):
        if self._start_run_error:
            raise self._start_run_error
        return 99

    def upsert_snapshot(self, listing_id, scraped):
        self.upserted.append((listing_id, scraped))

    def finish_run(self, result):
        if self._finish_run_error:
            raise self._finish_run_error
        self.finished = result

    def mark_alerted(self, run_id):
        if self._mark_alerted_error:
            raise self._mark_alerted_error
        self.alerted_run_id = run_id


class _FakeNotifier:
    def __init__(self):
        self.messages: list[str] = []

    async def send(self, message):
        self.messages.append(message)


class _StubScraper(BaseScraper):
    def __init__(self, *args, fetch_results: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fetch_results = fetch_results or {}

    async def fetch_listing(self, page, listing):
        result = self._fetch_results[listing.id]
        if isinstance(result, Exception):
            raise result
        return result

    async def _build_context(self, playwright):
        return _FakeContext()


@pytest.fixture(autouse=True)
def _fast_and_offline(monkeypatch):
    # No real Playwright driver, no real robots.txt fetch, no real sleeps —
    # the run() control flow (skip/robots/backoff/coverage/alerting logic) is
    # what's under test here, not Playwright or network I/O.
    monkeypatch.setattr(base_module, "async_playwright", lambda: _FakeAsyncPlaywrightCM())

    async def no_op_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(base_module, "sleep_jitter", no_op_sleep)


def _scraped_price():
    return ScrapedPrice(
        price=1.0,
        regular_price=1.0,
        price_per_unit=1.0,
        unit_basis="EUR/kg",
        is_promotion=False,
        promotion_label=None,
        in_stock=True,
        raw_payload={},
    )


async def test_run_skips_store_blocked_earlier_today_without_touching_playwright():
    today_iso = datetime.now(timezone.utc).isoformat()
    db = _FakeDb(listings=[], latest_run={"blocked": True, "started_at": today_iso})
    notifier = _FakeNotifier()
    scraper = _StubScraper(config=_make_config(), db=db, notifier=notifier)

    result = await scraper.run(mode="basket")

    assert result.status == "skipped"
    assert result.attempted == 0
    assert result.error_summary == "skipped: blocked earlier today"
    # Never got as far as finishing a run or alerting — it returned before
    # start_run() was ever called.
    assert db.finished is None
    assert notifier.messages == []


async def test_run_reports_full_coverage_and_does_not_alert_when_everything_succeeds(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1), _make_listing(2)]
    db = _FakeDb(listings=listings)
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: _scraped_price(), 2: _scraped_price()},
    )

    result = await scraper.run(mode="basket")

    assert result.status == "success"
    assert result.attempted == 2
    assert result.ok == 2
    assert result.failed == 0
    assert result.coverage == pytest.approx(1.0)
    assert len(db.upserted) == 2
    assert db.finished is result
    assert notifier.messages == []  # full coverage -> no alert
    assert db.alerted_run_id is None


async def test_run_skips_already_captured_and_robots_disallowed_listings(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots(disallowed_ids=frozenset({2})))
    listings = [_make_listing(1), _make_listing(2), _make_listing(3)]
    db = _FakeDb(listings=listings, already_captured_ids=frozenset({1}))
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={3: _scraped_price()},
    )

    result = await scraper.run(mode="basket")

    # listing 1: already captured -> skipped entirely (not attempted, not failed)
    # listing 2: robots-disallowed -> failed, but NOT counted in attempted
    # listing 3: succeeds -> attempted + ok
    assert result.attempted == 1
    assert result.ok == 1
    assert result.failed == 1
    assert "disallowed by robots.txt" in result.error_summary
    assert [lid for lid, _ in db.upserted] == [3]


async def test_run_marks_partial_and_alerts_when_coverage_drops_below_threshold(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1), _make_listing(2)]
    db = _FakeDb(listings=listings)
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: _scraped_price(), 2: FetchFailed("boom")},
    )

    result = await scraper.run(mode="basket")

    assert result.status == "partial"
    assert result.attempted == 2
    assert result.ok == 1
    assert result.failed == 1
    assert result.coverage == pytest.approx(0.5)
    # Below COVERAGE_ALERT_THRESHOLD (0.85) -> alerted, and the dedup flag set.
    assert len(notifier.messages) == 1
    assert "PARTIAL" in notifier.messages[0]
    assert db.alerted_run_id == 99


async def test_run_stops_and_marks_failed_on_block_detected(monkeypatch):
    from scraper.models import BlockDetected

    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1), _make_listing(2)]
    db = _FakeDb(listings=listings)
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: BlockDetected("captcha")},
    )

    result = await scraper.run(mode="basket")

    assert result.status == "failed"
    assert result.blocked is True
    # Loop breaks immediately on BlockDetected — listing 2 is never attempted.
    assert result.attempted == 1
    assert result.failed == 1
    assert len(notifier.messages) == 1


async def test_run_status_is_failed_when_every_listing_fails(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1)]
    db = _FakeDb(listings=listings)
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: FetchFailed("boom")},
    )

    result = await scraper.run(mode="basket")

    assert result.status == "failed"
    assert result.ok == 0
    assert result.coverage == pytest.approx(0.0)
    assert len(notifier.messages) == 1


async def test_run_catches_unexpected_exception_from_fetch_listing_and_keeps_going(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1), _make_listing(2)]
    db = _FakeDb(listings=listings)
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: RuntimeError("playwright timeout"), 2: _scraped_price()},
    )

    result = await scraper.run(mode="basket")

    # An unexpected (non-FetchFailed/BlockDetected) exception is recorded and
    # the loop continues to the next listing rather than aborting the run.
    assert result.attempted == 2
    assert result.ok == 1
    assert result.failed == 1
    assert "unexpected error" in result.error_summary
    assert [lid for lid, _ in db.upserted] == [2]


async def test_run_alerts_and_reraises_when_start_run_fails():
    db = _FakeDb(listings=[], start_run_error=RuntimeError("db unreachable"))
    notifier = _FakeNotifier()
    scraper = _StubScraper(config=_make_config(), db=db, notifier=notifier)

    with pytest.raises(RuntimeError, match="db unreachable"):
        await scraper.run(mode="basket")

    assert len(notifier.messages) == 1
    assert "FAILED TO START" in notifier.messages[0]


async def test_run_alerts_and_reraises_when_finish_run_fails(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1)]
    db = _FakeDb(listings=listings, finish_run_error=RuntimeError("write conflict"))
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(), db=db, notifier=notifier, fetch_results={1: _scraped_price()}
    )

    with pytest.raises(RuntimeError, match="write conflict"):
        await scraper.run(mode="basket")

    # Success on coverage grounds alone wouldn't normally alert, but a
    # finish_run() failure must still surface a Telegram message before the
    # exception propagates — GitHub's native failure email isn't the only signal.
    assert len(notifier.messages) == 1
    assert "DB write failed while finishing this run" in notifier.messages[0]


async def test_run_swallows_mark_alerted_failure(monkeypatch):
    monkeypatch.setattr(base_module, "RobotsChecker", lambda base_url, user_agent: _FakeRobots())
    listings = [_make_listing(1)]
    db = _FakeDb(
        listings=listings,
        mark_alerted_error=RuntimeError("dedup flag write failed"),
    )
    notifier = _FakeNotifier()
    scraper = _StubScraper(
        config=_make_config(),
        db=db,
        notifier=notifier,
        fetch_results={1: FetchFailed("boom")},
    )

    # mark_alerted() raising must not blow up the run — losing the dedup flag
    # just risks a duplicate alert next time, which beats losing the alert.
    result = await scraper.run(mode="basket")

    assert result.status == "failed"
    assert len(notifier.messages) == 1
    assert db.alerted_run_id is None
