"""Pluggable notifier interface (spec §8) — Telegram today, Discord/Null
implementations can be added later without touching call sites."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    @abstractmethod
    async def send(self, message: str) -> None: ...
