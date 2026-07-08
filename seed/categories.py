"""Seed ECOICOP v2 leaf categories (spec §4.2).

Codes are standard UN COICOP 2018 / ECOICOP v2 classification (5-digit leaf
level), pinned by hand against real Eurostat weight data (`weights/eurostat.py`
returns every code Portugal reports, used to confirm each leaf exists before
adding it here). `parent_id` is left null — the full division/group/class
ancestor hierarchy only matters once the category crawl needs to walk it (it
doesn't). `hicp_weight`/`weight_year` are populated separately by
weights/eurostat.py, never hardcoded here.

**Real bug found and fixed (2026-07-08)**: "Cheese and curd" and "Eggs" were
originally seeded under codes `01.1.4.4`/`01.1.4.6` — plausible-looking but
wrong. Eurostat's actual PT breakdown of 01.1.4 (Milk, cheese and eggs) is
finer than assumed: .1 fresh whole milk, .2 fresh low-fat milk, .3 preserved
milk, .4 yoghurt, .5 cheese and curd, .6 other milk products, .7 eggs. This
was caught by decoding Eurostat's raw `CPxxxxx` codes with our own
`to_dotted_ecoicop()` and cross-checking against Eurostat's official English
labels for those exact codes — both independently confirmed the correct
codes are `01.1.4.5` (cheese) and `01.1.4.7` (eggs), not `.4`/`.6`. Fixed in
place (same category `id`, so `products.category_id` FKs were untouched) and
weights re-synced. Historical `inflation_metrics` rows computed before the
fix keep the old (wrong) `dimension_value` — a small, accepted, disclosed
discontinuity in those two categories' time series rather than rewriting
already-computed history. Lesson: always verify a new code against Eurostat's
own labels for that exact code, not just a plausible-sounding COICOP name.
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
    {"ecoicop2_code": "01.1.4.7", "name_pt": "Ovos", "name_en": "Eggs", "level": 5},
    {"ecoicop2_code": "01.1.5.3", "name_pt": "Azeite", "name_en": "Olive oil", "level": 5},
    {"ecoicop2_code": "01.1.1.1", "name_pt": "Arroz", "name_en": "Rice", "level": 5},
    {
        "ecoicop2_code": "01.1.4.5",
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
    {
        "ecoicop2_code": "01.1.1.2",
        "name_pt": "Farinhas e outros cereais",
        "name_en": "Flours and other cereals",
        "level": 5,
    },
    {"ecoicop2_code": "01.1.2.1", "name_pt": "Carne de bovino", "name_en": "Beef and veal", "level": 5},
    {"ecoicop2_code": "01.1.2.2", "name_pt": "Carne de suíno", "name_en": "Pork", "level": 5},
    {
        "ecoicop2_code": "01.1.3.1",
        "name_pt": "Peixe fresco ou refrigerado",
        "name_en": "Fresh or chilled fish",
        "level": 5,
    },
    {
        "ecoicop2_code": "01.1.3.5",
        "name_pt": "Peixe seco, fumado ou salgado",
        "name_en": "Dried, smoked or salted fish and seafood",
        "level": 5,
    },
    {"ecoicop2_code": "01.1.4.4", "name_pt": "Iogurte", "name_en": "Yoghurt", "level": 5},
    {
        "ecoicop2_code": "01.1.6.1",
        "name_pt": "Fruta fresca ou refrigerada",
        "name_en": "Fresh fruit",
        "level": 5,
    },
    {
        "ecoicop2_code": "01.1.7.1",
        "name_pt": "Legumes frescos ou refrigerados",
        "name_en": "Vegetables",
        "level": 5,
    },
]


def seed_categories(supabase_client) -> None:
    supabase_client.table("categories").upsert(
        SEED_CATEGORIES, on_conflict="ecoicop2_code"
    ).execute()
