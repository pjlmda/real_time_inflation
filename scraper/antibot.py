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

import httpx

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

# Shared across all store scrapers (spec §7 backoff rule) — identical set for
# every store so far, kept here rather than duplicated per store module.
RETRYABLE_STATUS = {403, 429, 500, 502, 503, 504}


class RobotsChecker:
    """Wraps stdlib `urllib.robotparser` for a single store's robots.txt.

    Fetches via httpx rather than robotparser's own `.read()` (stdlib
    `urllib`/`ssl`, which uses the OS/Python default trust store) — confirmed
    live that some CDNs (Lidl's myracloud, both France and Germany) present
    a certificate chain stdlib `ssl` can't complete (no AIA-chasing) even
    though the exact same domain works fine in a real browser or via httpx's
    certifi-based trust store. Parsing semantics still match stdlib's own
    `.read()`: 401/403 disallows everything, other 4xx allows everything (no
    robots.txt present), 2xx parses the content normally.
    """

    def __init__(self, base_url: str, user_agent: str):
        self.parser = robotparser.RobotFileParser()
        robots_url = base_url.rstrip("/") + "/robots.txt"
        self.parser.set_url(robots_url)
        self._fetch(robots_url)
        self.user_agent = user_agent

    def _fetch(self, robots_url: str) -> None:
        try:
            resp = httpx.get(robots_url, timeout=15.0, follow_redirects=True)
        except httpx.HTTPError:
            # Unreachable robots.txt is treated the same as stdlib's
            # behavior for a non-4xx failure: assume everything is allowed
            # rather than blocking the whole run over a transient fetch issue.
            self.parser.allow_all = True
            return

        if resp.status_code in (401, 403):
            self.parser.disallow_all = True
        elif resp.status_code >= 400:
            self.parser.allow_all = True
        else:
            self.parser.parse(resp.text.splitlines())

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
