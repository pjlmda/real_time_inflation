"""Seed the pilot's ECOICOP v2 leaf categories (spec §4.2).

Codes are standard UN COICOP 2018 / ECOICOP v2 classification (5-digit leaf
level), pinned by hand for this small pilot set. `parent_id` is left null —
the full division/group/class ancestor hierarchy only matters once the
category crawl (Phase 2) needs to walk it. `hicp_weight`/`weight_year` are
populated separately by weights/eurostat.py, never hardcoded here.
"""
from __future__ import annotations

PILOT_CATEGORIES = [
    {"ecoicop2_code": "01.1.1.3", "name_pt": "Pão", "name_en": "Bread", "level": 5},
    {
        "ecoicop2_code": "01.1.1.6",
        "name_pt": "Massas alimentícias e cuscuz",
        "name_en": "Pasta products and couscous",
        "level": 5,
    },
    {"ecoicop2_code": "01.1.4.1", "name_pt": "Leite fresco", "name_en": "Fresh milk", "level": 5},
    {"ecoicop2_code": "01.1.4.6", "name_pt": "Ovos", "name_en": "Eggs", "level": 5},
    {"ecoicop2_code": "01.1.5.3", "name_pt": "Azeite", "name_en": "Olive oil", "level": 5},
]


def seed_categories(supabase_client) -> None:
    supabase_client.table("categories").upsert(
        PILOT_CATEGORIES, on_conflict="ecoicop2_code"
    ).execute()
