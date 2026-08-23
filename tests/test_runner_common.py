from scraper.models import RunResult
from scraper.runner_common import ERROR_SUMMARY_LIMIT, send_run_alert, summarize_error_reasons


class _FakeNotifier:
    def __init__(self, send_error: Exception | None = None):
        self.messages: list[str] = []
        self._send_error = send_error

    async def send(self, message):
        if self._send_error:
            raise self._send_error
        self.messages.append(message)


class _FakeDb:
    def __init__(self, mark_alerted_error: Exception | None = None):
        self._mark_alerted_error = mark_alerted_error
        self.alerted_run_id = None

    def mark_alerted(self, run_id):
        if self._mark_alerted_error:
            raise self._mark_alerted_error
        self.alerted_run_id = run_id


def _make_result(error_summary=None, status="partial"):
    return RunResult(
        run_id=42, attempted=2, ok=1, failed=1, status=status, coverage=0.5, error_summary=error_summary
    )


async def test_send_run_alert_escapes_dynamic_error_summary_but_not_literal_bold_markers():
    # error_summary can embed raw scraped page text (e.g. a Drive-bootstrap
    # diagnostic snippet) - it must be escaped so it can't break Telegram's
    # Markdown parser, while the literal *config_name*/*status* formatting
    # this function itself writes stays unescaped.
    notifier = _FakeNotifier()
    db = _FakeDb()
    result = _make_result(error_summary="listing failed: price_per_kg *promo* not found [details]")

    await send_run_alert(notifier, db, "test-store", result, "scrape run")

    message = notifier.messages[0]
    assert "price\\_per\\_kg \\*promo\\* not found \\[details]" in message
    assert message.startswith("*test-store*")  # our own bold markup, not escaped


async def test_send_run_alert_escapes_db_error():
    notifier = _FakeNotifier()
    db = _FakeDb()
    result = _make_result(error_summary=None)

    await send_run_alert(notifier, db, "test-store", result, "scrape run", db_error=RuntimeError("write_conflict"))

    assert "write\\_conflict" in notifier.messages[0]


async def test_send_run_alert_marks_alerted_on_successful_delivery():
    notifier = _FakeNotifier()
    db = _FakeDb()
    result = _make_result()

    await send_run_alert(notifier, db, "test-store", result, "scrape run")

    assert db.alerted_run_id == 42


async def test_send_run_alert_does_not_mark_alerted_when_delivery_fails():
    # Real behavior this guards: marking "alerted" after a failed send would
    # wrongly suppress a real retry next run, since the message never
    # actually reached anyone.
    notifier = _FakeNotifier(send_error=RuntimeError("telegram rejected the message"))
    db = _FakeDb()
    result = _make_result()

    await send_run_alert(notifier, db, "test-store", result, "scrape run")

    assert db.alerted_run_id is None


def test_summarize_error_reasons_returns_none_when_empty():
    assert summarize_error_reasons([]) is None


def test_summarize_error_reasons_joins_reasons_under_the_limit():
    reasons = ["listing 1: not carried", "listing 2: not carried"]

    assert summarize_error_reasons(reasons) == "listing 1: not carried; listing 2: not carried"


def test_summarize_error_reasons_flags_omitted_count_past_the_limit():
    # Regression test: this used to be error_reasons[:5] inline, silently
    # dropping every reason past the 5th with no indication anything was
    # omitted - found while investigating Auchan France Marseille listings
    # that looked like they'd stopped being scraped entirely when they were
    # actually failing every day, just past the old cutoff.
    reasons = [f"listing {i}: not carried" for i in range(ERROR_SUMMARY_LIMIT + 3)]

    summary = summarize_error_reasons(reasons)

    assert summary.startswith("listing 0: not carried")
    assert summary.endswith("and 3 more")
    assert summary.count("listing") == ERROR_SUMMARY_LIMIT
