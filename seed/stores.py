"""Seed `stores` from config/stores.yaml — config-driven, multi-store from
day one (spec §1), even though only Continente is scraped in the pilot."""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "stores.yaml"


def load_store_rows() -> list[dict]:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return [
        {
            "name": s["name"],
            "slug": s["slug"],
            "base_url": s["base_url"],
            "country": "PT",
        }
        for s in raw["stores"]
    ]


def seed_stores(supabase_client) -> None:
    rows = load_store_rows()
    supabase_client.table("stores").upsert(rows, on_conflict="slug").execute()
