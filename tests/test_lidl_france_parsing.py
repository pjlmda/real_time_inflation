import pytest

from scraper.lidl_france import _parse_euro, _parse_footer, parse_package_size
from scraper.models import FetchFailed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.20 €", 1.20),
        ("3.35 €", 3.35),
        ("16.99 €", 16.99),
    ],
)
def test_parse_euro_matches_real_lidl_france_formats(text, expected):
    assert _parse_euro(text) == pytest.approx(expected)


def test_parse_euro_raises_on_unparseable_text():
    with pytest.raises(FetchFailed):
        _parse_euro("indisponible")


def test_parse_footer_reads_explicit_price_per_kg_line():
    # Real footer text confirmed live for "Pain de mie" (bread).
    footer = "750 g\n1 kg = 1,60 €\n"
    assert _parse_footer(footer, price=1.20) == (pytest.approx(1.60), "EUR/kg")


def test_parse_footer_reads_explicit_price_per_liter_line():
    footer = "2 x 425 ml\n1 L = 6,06 €\n"
    assert _parse_footer(footer, price=5.15) == (pytest.approx(6.06), "EUR/L")


def test_parse_footer_treats_le_kilo_as_variable_weight_priced_per_kg():
    # Real footer text confirmed live for a beef cut sold by weight, no
    # fixed package size ("Le kilo" instead of e.g. "500 g").
    footer = "Le kilo\n"
    assert _parse_footer(footer, price=16.99) == (16.99, "EUR/kg")


def test_parse_footer_falls_back_to_deriving_from_package_size_when_no_ppu_line():
    # Real footer text confirmed live for olive oil - no explicit "1 L = X €"
    # line, just the package size itself.
    footer = "1 L\n\n"
    assert _parse_footer(footer, price=5.59) == (pytest.approx(5.59), "EUR/L")


def test_parse_package_size_single_pack():
    assert parse_package_size("750 g\n1 kg = 1,60 €\n") == (750.0, "g")


def test_parse_package_size_multipack_uses_total_not_per_unit():
    # Real footer text confirmed live for yoghurt - 8x125g totals 1000g,
    # matching this project's established multi-pack convention.
    assert parse_package_size("8 x 125 g\n1 kg = 2,36 €\n") == (1000.0, "g")


def test_parse_package_size_multipack_liters():
    assert parse_package_size("2 x 425 ml\n1 L = 6,06 €\n") == (850.0, "ml")


def test_parse_package_size_converts_centiliters_to_milliliters():
    # products.package_unit has no 'cl' option in its DB check constraint
    # ('L', 'kg', 'un', 'g', 'ml' only) - centiliters must convert.
    assert parse_package_size("75 cl\n1 L = 8,65 €\n") == (750.0, "ml")


def test_parse_package_size_raises_when_no_size_present():
    with pytest.raises(ValueError):
        parse_package_size("Le kilo\n")
