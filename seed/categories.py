"""Seed ECOICOP v2 leaf categories (spec §4.2).

Codes are standard UN COICOP 2018 / ECOICOP v2 classification (5-digit leaf
level), pinned by hand against real Eurostat weight data (`weights/eurostat.py`
returns every code Portugal reports, used to confirm each leaf exists before
adding it here). `parent_id` is left null — the full division/group/class
ancestor hierarchy only matters once the category crawl needs to walk it (it
doesn't). `hicp_weight`/`weight_year` are populated separately by
weights/eurostat.py, never hardcoded here.
"""
from __future__ import annotations

SEED_CATEGORIES = [
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
    {"ecoicop2_code": "01.1.1.1", "name_pt": "Arroz", "name_en": "Rice", "level": 5},
    {
        "ecoicop2_code": "01.1.4.4",
        "name_pt": "Queijo e requeijão",
        "name_en": "Cheese and curd",
        "level": 5,
    },
    {"ecoicop2_code": "01.1.2.4", "name_pt": "Carne de aves", "name_en": "Poultry", "level": 5},
    {
        "ecoicop2_code": "01.1.3.6",
        "name_pt": "Peixe e marisco preparado ou em conserva",
        "name_en": "Preserved or processed fish and seafood",
        "level": 5,
    },
    {"ecoicop2_code": "02.1.2.1", "name_pt": "Vinho de uvas", "name_en": "Wine from grapes", "level": 5},
    {
        "ecoicop2_code": "12.1.3.2",
        "name_pt": "Produtos de higiene pessoal",
        "name_en": "Personal care articles and products",
        "level": 5,
    },
]


def seed_categories(supabase_client) -> None:
    supabase_client.table("categories").upsert(
        SEED_CATEGORIES, on_conflict="ecoicop2_code"
    ).execute()
