from pathlib import Path

import httpx
import pytest

from scraper.antibot import RetryableHttpError, RobotsChecker, detect_block, jittered_delay, with_backoff
from scraper.models import BlockDetected, FetchFailed

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeAsyncClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def get(self, url, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


def _patch_robots_response(monkeypatch, status_code: int, text: str = ""):
    def fake_client(*args, **kwargs):
        request = httpx.Request("GET", "https://example.com/robots.txt")
        response = httpx.Response(status_code, text=text, request=request)
        return _FakeAsyncClient(response=response)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


def test_detect_block_on_captcha_page():
    html = (FIXTURES / "captcha_page.html").read_text(encoding="utf-8")
    assert detect_block(html) is True


def test_detect_block_false_on_normal_page():
    html = (FIXTURES / "normal_page.html").read_text(encoding="utf-8")
    assert detect_block(html) is False


def test_jittered_delay_within_expected_range_most_of_the_time():
    # 10% chance of a long-pause outlier per antibot.jittered_delay — sample
    # enough draws that the base range dominates without being flaky.
    samples = [jittered_delay(2, 5) for _ in range(200)]
    in_range = [s for s in samples if 2 <= s <= 5]
    assert len(in_range) > 150


@pytest.mark.asyncio
async def test_with_backoff_returns_on_first_success():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        return "ok"

    result = await with_backoff(fn)
    assert result == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_with_backoff_retries_then_succeeds():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RetryableHttpError(status=503, retry_after=0)
        return "ok"

    result = await with_backoff(fn, max_attempts=4)
    assert result == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_with_backoff_raises_fetch_failed_after_max_attempts():
    async def fn():
        raise RetryableHttpError(status=503, retry_after=0)

    with pytest.raises(FetchFailed):
        await with_backoff(fn, max_attempts=2)


@pytest.mark.asyncio
async def test_with_backoff_never_retries_block_detected():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        raise BlockDetected("captcha")

    with pytest.raises(BlockDetected):
        await with_backoff(fn, max_attempts=4)
    assert calls == 1


@pytest.mark.asyncio
async def test_robots_checker_parses_content_on_200(monkeypatch):
    _patch_robots_response(monkeypatch, 200, text="User-agent: *\nDisallow: /admin/\n")

    checker = await RobotsChecker("https://example.com", "test-agent").load()

    assert checker.allowed("https://example.com/product/1") is True
    assert checker.allowed("https://example.com/admin/panel") is False


@pytest.mark.asyncio
async def test_robots_checker_disallows_everything_on_403(monkeypatch):
    # Real bug this guards against: stdlib urllib/ssl can't complete some
    # CDNs' certificate chains (confirmed live for Lidl's myracloud CDN)
    # even though the same domain works fine via httpx/a real browser -
    # RobotsChecker now fetches via httpx specifically to avoid that. This
    # test covers the status-code semantics that must still match stdlib
    # robotparser's own documented behavior for 401/403 (disallow all).
    _patch_robots_response(monkeypatch, 403)

    checker = await RobotsChecker("https://example.com", "test-agent").load()

    assert checker.allowed("https://example.com/anything") is False


@pytest.mark.asyncio
async def test_robots_checker_allows_everything_on_404(monkeypatch):
    _patch_robots_response(monkeypatch, 404)

    checker = await RobotsChecker("https://example.com", "test-agent").load()

    assert checker.allowed("https://example.com/anything") is True


@pytest.mark.asyncio
async def test_robots_checker_allows_everything_when_unreachable(monkeypatch):
    def fake_client(*args, **kwargs):
        return _FakeAsyncClient(exc=httpx.ConnectError("connection refused"))

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)

    checker = await RobotsChecker("https://example.com", "test-agent").load()

    assert checker.allowed("https://example.com/anything") is True
