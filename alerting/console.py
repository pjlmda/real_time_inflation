"""Fallback notifier for local runs before Telegram credentials exist. Never
used by the scheduled GitHub Action — scrape.yml always provides Telegram
secrets, so a real run there always alerts for real."""
from __future__ import annotations

from alerting.base import Notifier


class ConsoleNotifier(Notifier):
    async def send(self, message: str) -> None:
        print(f"[ALERT - no Telegram configured]\n{message}")
