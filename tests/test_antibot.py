from pathlib import Path

import pytest

from scraper.antibot import RetryableHttpError, detect_block, jittered_delay, with_backoff
from scraper.models import BlockDetected, FetchFailed

FIXTURES = Path(__file__).parent / "fixtures"


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
