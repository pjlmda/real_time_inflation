from scraper.runner_common import ERROR_SUMMARY_LIMIT, summarize_error_reasons


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
