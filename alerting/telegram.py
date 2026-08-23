"""Telegram Bot API notifier — plain HTTPS POST, no SDK needed (spec §8)."""
from __future__ import annotations

import httpx

from alerting.base import Notifier

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


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
