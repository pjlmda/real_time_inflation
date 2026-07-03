"""Anti-bot / resilient scraping layer (spec §7) — shared by every store
scraper via BaseScraper. Kept as small composable helpers rather than a
framework so each piece (robots check, backoff, block detection, stealth) is
independently testable.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from urllib import robotparser

from scraper.models import BlockDetected, FetchFailed

# Explicit, auditable stealth patches — preferred over the `playwright-stealth`
# PyPI package, which tends to lag current Playwright/Chromium versions.
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['pt-PT', 'pt'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
"""

BLOCK_TEXT_MARKERS = [
    "verify you are human",
    "are you a robot",
    "unusual traffic",
    "captcha",
    "access denied",
    "attention required",
]


class RobotsChecker:
    """Wraps stdlib `urllib.robotparser` for a single store's robots.txt."""

    def __init__(self, base_url: str, user_agent: str):
        self.parser = robotparser.RobotFileParser()
        self.parser.set_url(base_url.rstrip("/") + "/robots.txt")
        self.parser.read()
        self.user_agent = user_agent

    def allowed(self, url: str) -> bool:
        return self.parser.can_fetch(self.user_agent, url)

    def crawl_delay(self) -> float | None:
        delay = self.parser.crawl_delay(self.user_agent)
        return float(delay) if delay else None


def jittered_delay(min_s: float, max_s: float) -> float:
    base = random.uniform(min_s, max_s)
    if random.random() < 0.1:  # occasional longer pause, per §7
        base += random.uniform(5, 15)
    return base


async def sleep_jitter(min_s: float, max_s: float) -> None:
    await asyncio.sleep(jittered_delay(min_s, max_s))


def detect_block(html: str) -> bool:
    """Heuristic CAPTCHA/block-page detection. False positives are cheap
    (we just stop this run early); false negatives are the real risk, so
    keep the marker list generic rather than store-specific."""
    lowered = html.lower()
    return any(marker in lowered for marker in BLOCK_TEXT_MARKERS)


async def apply_stealth(context) -> None:
    await context.add_init_script(STEALTH_INIT_SCRIPT)


@dataclass
class RetryableHttpError(Exception):
    status: int
    retry_after: float | None = None


async def with_backoff(fn, max_attempts: int = 4):
    """Exponential backoff honoring Retry-After when present; capped retries.
    BlockDetected is never retried — it propagates immediately so the caller
    can stop the whole run rather than hammering a block page."""
    attempt = 0
    delay = 2.0
    while True:
        attempt += 1
        try:
            return await fn()
        except BlockDetected:
            raise
        except RetryableHttpError as exc:
            if attempt >= max_attempts:
                raise FetchFailed(
                    f"exhausted {max_attempts} retries; last HTTP status {exc.status}"
                ) from exc
            wait = exc.retry_after if exc.retry_after is not None else delay
            await asyncio.sleep(wait)
            delay = min(delay * 2, 60)
