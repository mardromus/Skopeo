"""Pricing helpers. Prices are integer cents."""


def format_price(cents: int) -> str:
    return f"${cents // 100}.{cents % 100}"


def apply_discount(cents: int, percent: float) -> int:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(cents * (100 - percent) / 100)


def order_total(items: list[dict]) -> int:
    return sum(item["quantity"] * item["unit_price_cents"] for item in items)
