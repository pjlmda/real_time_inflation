from scraper import store_config as store_config_module


def test_load_store_config_reads_currency_per_store_not_hardcoded_eur(monkeypatch, tmp_path):
    # Real bug this guards: scraper/db.py used to hardcode currency="EUR"
    # for every store regardless of config/stores.yaml, only caught once a
    # USD store (Wegmans) existed - a US store's config must carry its own
    # currency rather than silently inheriting EUR.
    config = tmp_path / "stores.yaml"
    config.write_text(
        "stores:\n"
        "  - slug: continente\n"
        "    name: Continente\n"
        "    base_url: https://www.continente.pt\n"
        "    currency: EUR\n"
        "  - slug: wegmans-us\n"
        "    name: Wegmans\n"
        "    base_url: https://www.wegmans.com\n"
        "    currency: USD\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(store_config_module, "CONFIG_PATH", config)

    continente = store_config_module.load_store_config("continente")
    wegmans = store_config_module.load_store_config("wegmans-us")

    assert continente.currency == "EUR"
    assert wegmans.currency == "USD"


def test_load_store_config_defaults_to_eur_when_currency_omitted(monkeypatch, tmp_path):
    config = tmp_path / "stores.yaml"
    config.write_text(
        "stores:\n"
        "  - slug: legacy-store\n"
        "    name: Legacy Store\n"
        "    base_url: https://example.pt\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(store_config_module, "CONFIG_PATH", config)

    config_obj = store_config_module.load_store_config("legacy-store")

    assert config_obj.currency == "EUR"
