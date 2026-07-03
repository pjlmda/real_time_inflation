"""Telegram Bot API notifier — plain HTTPS POST, no SDK needed (spec §8)."""
from __future__ import annotations

import httpx

from alerting.base import Notifier

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID must both be set")
        self.token = token
        self.chat_id = chat_id

    async def send(self, message: str) -> None:
        url = API_URL.format(token=self.token)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
            )
            resp.raise_for_status()
