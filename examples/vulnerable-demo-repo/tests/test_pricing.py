import pytest

from shopfront.services.pricing import apply_discount, format_price, order_total


def test_format_price_whole_amount():
    assert format_price(1999) == "$19.99"


def test_format_price_pads_single_digit_cents():
    assert format_price(1905) == "$19.05"


def test_apply_discount():
    assert apply_discount(1000, 10) == 900


def test_apply_discount_rejects_invalid_percent():
    with pytest.raises(ValueError):
        apply_discount(1000, 150)


def test_order_total():
    assert order_total([{"quantity": 2, "unit_price_cents": 250}]) == 500
