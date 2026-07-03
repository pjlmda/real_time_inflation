"""Load a single store's scraping config from config/stores.yaml."""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"


@dataclass(frozen=True)
class StoreConfig:
    slug: str
    name: str
    base_url: str
    user_agent: str
    delay_seconds_min: float
    delay_seconds_max: float
    locale: str
    timezone_id: str


def load_store_config(slug: str) -> StoreConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    for entry in raw["stores"]:
        if entry["slug"] == slug:
            user_agents = entry.get("user_agents") or [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ]
            return StoreConfig(
                slug=entry["slug"],
                name=entry["name"],
                base_url=entry["base_url"],
                user_agent=random.choice(user_agents),  # one per session, not per request
                delay_seconds_min=entry.get("delay_seconds_min", 2),
                delay_seconds_max=entry.get("delay_seconds_max", 5),
                locale=entry.get("locale", "pt-PT"),
                timezone_id=entry.get("timezone_id", "Europe/Lisbon"),
            )
    raise ValueError(f"No store config found for slug={slug!r} in {CONFIG_PATH}")
