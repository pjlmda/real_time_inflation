from seed import stores as seed_stores_module


def test_load_store_rows_reads_country_per_store_not_hardcoded_pt(monkeypatch, tmp_path):
    # Real bug this guards: load_store_rows() used to hardcode country="PT"
    # for every store regardless of what config/stores.yaml actually said,
    # which would have silently mis-seeded the French Auchan entries as PT.
    config = tmp_path / "stores.yaml"
    config.write_text(
        "stores:\n"
        "  - slug: continente\n"
        "    name: Continente\n"
        "    base_url: https://www.continente.pt\n"
        "    country: PT\n"
        "  - slug: auchan-fr-paris\n"
        "    name: Auchan (Paris Drive)\n"
        "    base_url: https://www.auchan.fr\n"
        "    country: FR\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed_stores_module, "CONFIG_PATH", config)

    rows = seed_stores_module.load_store_rows()

    assert {r["slug"]: r["country"] for r in rows} == {
        "continente": "PT",
        "auchan-fr-paris": "FR",
    }


def test_load_store_rows_defaults_to_pt_when_country_omitted(tmp_path, monkeypatch):
    config = tmp_path / "stores.yaml"
    config.write_text(
        "stores:\n"
        "  - slug: legacy-store\n"
        "    name: Legacy Store\n"
        "    base_url: https://example.pt\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed_stores_module, "CONFIG_PATH", config)

    rows = seed_stores_module.load_store_rows()

    assert rows == [{"name": "Legacy Store", "slug": "legacy-store", "base_url": "https://example.pt", "country": "PT"}]
