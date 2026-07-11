import pytest

from scraper.models import FetchFailed
from scraper.wegmans import STORE_NUMBERS, _parse_unit_price, _to_scraped_price


def _make_item(**overrides):
    item = {
        "productID": "94427",
        "storeNumber": "134",
        "isAvailable": True,
        "isSoldAtStore": True,
        "price_inStore": {"amount": 2.99, "unitPrice": "$2.99/gallon"},
        "price_inStoreLoyalty": None,
        "discountType": None,
    }
    item.update(overrides)
    return item


def test_parse_unit_price_gallon():
    value, unit = _parse_unit_price("$2.99/gallon", fallback_price=2.99)
    assert value == 2.99
    assert unit == "USD/gallon"


def test_parse_unit_price_ounce():
    value, unit = _parse_unit_price("$0.06/ounce", fallback_price=0.99)
    assert value == 0.06
    assert unit == "USD/ounce"


def test_parse_unit_price_falls_back_when_missing():
    value, unit = _parse_unit_price("", fallback_price=3.49)
    assert value == 3.49
    assert unit == "USD/unit"


def test_to_scraped_price_raises_clear_error_when_not_carried_at_store():
    # Confirmed live 2026-07-11: fresh pork chops (product 54042) return
    # exactly this shape at the Manhattan store while carried fine at
    # Medford - a genuine, expected "not every location carries every
    # listing" gap, not a bug, matching Auchan France's two-Drive-locations
    # precedent. The error message must say so clearly, not just "no price".
    item = _make_item(isSoldAtStore=False, price_inStore=None, productName="Wegmans Boneless Center-Cut Pork Chops")

    with pytest.raises(FetchFailed, match="not carried at this store"):
        _to_scraped_price(item)


def test_to_scraped_price_reads_in_store_price_not_delivery():
    # Real, live-confirmed effect (see scraper/wegmans.py's module
    # docstring): price_delivery runs ~15-17% higher than price_inStore at
    # every store checked - in-store is the correct basis, matching every
    # other store scraped in this project.
    item = _make_item(price_inStore={"amount": 2.99, "unitPrice": "$2.99/gallon"})

    scraped = _to_scraped_price(item)

    assert scraped.price == 2.99
    assert scraped.price_per_unit == 2.99
    assert scraped.unit_basis == "USD/gallon"


def test_to_scraped_price_defaults_to_no_promotion_when_fields_absent():
    item = _make_item(price_inStoreLoyalty=None, discountType=None)

    scraped = _to_scraped_price(item)

    assert scraped.is_promotion is False
    assert scraped.regular_price == scraped.price


def test_to_scraped_price_detects_promotion_when_discount_type_present():
    item = _make_item(discountType="TPR")

    scraped = _to_scraped_price(item)

    assert scraped.is_promotion is True
    assert scraped.promotion_label == "TPR"


def test_to_scraped_price_detects_promotion_when_loyalty_price_differs():
    item = _make_item(price_inStoreLoyalty={"amount": 2.49})

    scraped = _to_scraped_price(item)

    assert scraped.is_promotion is True


def test_to_scraped_price_uses_in_stock_flag():
    item = _make_item(isAvailable=False)

    scraped = _to_scraped_price(item)

    assert scraped.in_stock is False


def test_store_numbers_cover_all_three_tracked_locations():
    assert set(STORE_NUMBERS.keys()) == {"wegmans-us-medford", "wegmans-us-nyc", "wegmans-us-fairfax"}
    assert STORE_NUMBERS["wegmans-us-medford"] == "134"
    assert STORE_NUMBERS["wegmans-us-nyc"] == "156"
    assert STORE_NUMBERS["wegmans-us-fairfax"] == "16"
