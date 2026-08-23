"""Pluggable notifier interface (spec §8) — Telegram today, Discord/Null
implementations can be added later without touching call sites."""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod

# Every secret this project's alert-sending code paths could plausibly have
# access to, via os.environ - checked defensively before a message is ever
# printed to a CI log (see safe_send's redact() call below). Not exhaustive
# by design (PROXY_URL/GH_ACTIONS_TOKEN aren't read by any alerting code
# path), just every credential a notifier's own process actually holds.
_SECRET_ENV_VARS = (
    "SUPABASE_SERVICE_KEY",
    "TELEGRAM_TOKEN",
    "EIA_API_KEY",
    "BLS_API_KEY",
)


def redact(text: str) -> str:
    """Replace any currently-configured secret value found verbatim in
    `text` with "***". Defense-in-depth for safe_send()'s stderr fallback:
    escape_markdown() backslash-prefixes special characters, which can
    make an otherwise-masked secret (GitHub Actions masks by exact string
    match) no longer match that mask once escaped - e.g. a base64url JWT
    or an `sb_secret_...` key containing "_" would print with a stray
    backslash inserted, defeating CI's own secret redaction. This never
    fires today (nothing currently puts a raw secret into an alert
    message - see fuel/eia.py's own care around this), but the point of a
    defensive layer is to hold even after a future bug, not just today's
    code."""
    for var in _SECRET_ENV_VARS:
        value = os.environ.get(var)
        if value:
            text = text.replace(value, "***")
    return text


class Notifier(ABC):
    @abstractmethod
    async def send(self, message: str) -> None: ...


async def safe_send(notifier: Notifier, message: str) -> bool:
    """Every alert call site must go through this instead of calling
    notifier.send() directly. A delivery failure (Telegram rejecting
    unescaped Markdown, a revoked token, a network error, ...) must never
    crash the caller, and the message content must never be lost even
    when delivery fails.

    Real incident this fixes: scraper/auchan_france.py's Drive-bootstrap
    diagnostic message was built successfully, but Telegram rejected it
    with HTTP 400 (unescaped Markdown special characters in scraped page
    text - see alerting.telegram.escape_markdown). Nothing caught that,
    so the whole scraper process crashed with an uncaught exception before
    the diagnostic content was printed anywhere - not delivered, not
    logged, not readable by anyone.

    Returns whether delivery actually succeeded, so callers with a dedup
    flag (e.g. scrape_runs.alerted) only set it on confirmed delivery -
    marking "alerted" after a failed send would wrongly suppress a real
    retry next run."""
    try:
        await notifier.send(message)
        return True
    except Exception as exc:  # noqa: BLE001 - must never propagate; a notifier
        # failure crashing the whole run is exactly the bug this fixes.
        print(
            f"WARNING: alert delivery failed ({type(exc).__name__}: {exc}) — message was:\n{redact(message)}",
            file=sys.stderr,
        )
        return False
