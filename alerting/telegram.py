"""Telegram Bot API notifier — plain HTTPS POST, no SDK needed (spec §8)."""
from __future__ import annotations

import httpx

from alerting.base import Notifier

API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram's legacy Markdown (parse_mode="Markdown" below, NOT MarkdownV2)
# requires these characters to be backslash-escaped wherever they're not
# meant as formatting syntax, or the whole sendMessage call is rejected
# with a flat HTTP 400 (no partial delivery). Real incident this guards:
# scraper/auchan_france.py's Drive-bootstrap diagnostic embeds raw scraped
# page text in an alert message - an unescaped "_"/"*"/"`"/"[" in that text
# got Telegram's parser to 400 the whole alert, and because nothing caught
# the failure, the scraper process crashed before the diagnostic content
# was ever visible anywhere (see alerting.base.safe_send).
#
# Backslash MUST be escaped first, before the other four: Telegram reads a
# backslash immediately followed by one of the special characters as ONE
# escaped-literal token (e.g. backslash-underscore = a literal underscore).
# If "_" were escaped before "\\", a source string already containing a raw
# backslash next to an underscore (any Windows path - confirmed live to
# still 400 when escaped in the wrong order) would end up with that
# backslash re-paired with the newly-inserted escape backslash, producing
# an unescaped bare underscore again. Escaping "\\" to "\\\\" first means
# every original backslash is already doubled (so it can never re-pair
# with anything inserted afterward) before the underscore/asterisk/etc.
# passes run - live-verified via a real Telegram send with both orderings.
_MARKDOWN_SPECIAL_CHARS = ("\\", "_", "*", "`", "[")

# Telegram's hard per-message limit; sendMessage rejects anything longer
# with its own 400. A long error_summary (ERROR_SUMMARY_LIMIT=20 joined
# reasons, further expanded by escaping) could hit this even after the
# Markdown fix above - same failure shape, different cause, so truncate
# here rather than trusting every call site to remember.
MAX_MESSAGE_LENGTH = 4000


def escape_markdown(text: str) -> str:
    """Escape untrusted/dynamic text (scraped content, exception messages)
    before embedding it in a Telegram message. Apply to specific dynamic
    fields only, never to a whole message - intentional literal markup
    like f"*{name}*" must still render as bold."""
    for char in _MARKDOWN_SPECIAL_CHARS:
        text = text.replace(char, f"\\{char}")
    return text


class TelegramSendFailed(Exception):
    """Telegram declined or couldn't be reached for this message. Raised
    explicitly with a status-code-only message rather than letting
    httpx.HTTPStatusError propagate — its default string representation
    embeds the full request URL, which contains the bot token in
    cleartext (API_URL below), the same leak shape fixed in
    fuel/eia.py's EiaRequestFailed. `raise ... from None` matters here
    too: without it, the leaking original is still reachable via the
    traceback's chained "During handling of the above exception"
    context."""


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must both be set")
        self.token = token
        self.chat_id = chat_id

    async def send(self, message: str) -> None:
        if len(message) > MAX_MESSAGE_LENGTH:
            # rstrip a dangling trailing backslash before appending the
            # ellipsis - escape_markdown() always emits backslashes in
            # pairs (either "\\\\" for a literal backslash or "\<char>" for
            # an escaped special char), so a naive slice can land exactly
            # between a backslash and the character it was escaping,
            # leaving an incomplete escape sequence that would 400 all
            # over again - the same failure this truncation is meant to
            # prevent.
            message = message[: MAX_MESSAGE_LENGTH - 1].rstrip("\\") + "…"
        url = API_URL.format(token=self.token)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TelegramSendFailed(f"Telegram API returned HTTP {exc.response.status_code}") from None
        except httpx.RequestError as exc:
            raise TelegramSendFailed(f"Telegram API request failed: {type(exc).__name__}") from None
