"""Legacy price lookup kept for backwards compatibility."""

import warnings

from shopfront.services.pricing import format_price

PRICES = {"SKU-1": 1999, "SKU-2": 450, "SKU-3": 12000}


def legacy_price_lookup(sku: str) -> str:
    """Deprecated: use the catalogue service instead."""
    warnings.warn(
        "legacy_price_lookup is deprecated; use the catalogue service",
        DeprecationWarning,
        stacklevel=2,
    )
    return format_price(PRICES.get(sku, 0))
