from scraper.wegmans import _parse_ppu, _parse_price


def test_parse_price_basic():
    assert _parse_price("Price is:\n$2.99/ea") == 2.99


def test_parse_price_large_family_pack():
    assert _parse_price("Price is:\n$16.49/ea") == 16.49


def test_parse_ppu_gallon():
    value, unit = _parse_ppu("Unit price is:\n($2.99/gallon)", price=2.99)
    assert value == 2.99
    assert unit == "USD/gallon"


def test_parse_ppu_pound_with_period():
    value, unit = _parse_ppu("Unit price is:\n($6.49/lb.)", price=6.49)
    assert value == 6.49
    assert unit == "USD/lb."


def test_parse_ppu_ounce():
    value, unit = _parse_ppu("Unit price is:\n($0.37/ounce)", price=2.99)
    assert value == 0.37
    assert unit == "USD/ounce"


def test_parse_ppu_each_for_eggs():
    value, unit = _parse_ppu("Unit price is:\n($0.21/ea)", price=2.49)
    assert value == 0.21
    assert unit == "USD/ea"


def test_parse_ppu_fl_oz_with_internal_dots():
    value, unit = _parse_ppu("Unit price is:\n($0.35/fl. oz.)", price=5.99)
    assert value == 0.35
    assert unit == "USD/fl. oz."


def test_parse_ppu_falls_back_when_absent():
    value, unit = _parse_ppu("", price=3.49)
    assert value == 3.49
    assert unit == "USD/unit"
