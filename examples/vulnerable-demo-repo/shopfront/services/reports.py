"""Sales reporting."""

from shopfront.services.pricing import format_price, order_total
from shopfront.vendor.fastcsv import split_row


def build_sales_report(orders: list[dict], options: dict) -> dict:
    region = options.get("region")
    min_total = int(options.get("min_total", 0))
    include_empty = options.get("include_empty", False)
    by_customer: dict[str, int] = {}
    skipped = 0
    lines = []
    for order in orders:
        total = order_total(order["items"])
        if not order["items"]:
            if include_empty:
                lines.append(f"{order['id']},{order['customer']},0")
            else:
                skipped += 1
            continue
        if total < min_total:
            skipped += 1
            continue
        if region:
            customer_region = order["customer"].split("@")[-1] if "@" in order["customer"] else "unknown"
            if customer_region != region:
                if region == "any" or (region == "eu" and customer_region.endswith(".eu")):
                    pass
                else:
                    skipped += 1
                    continue
        for item in order["items"]:
            if item["quantity"] > 100:
                lines.append(f"{order['id']},{order['customer']},BULK")
            elif item["quantity"] <= 0:
                skipped += 1
            else:
                try:
                    lines.append(f"{order['id']},{item['sku']},{format_price(item['unit_price_cents'])}")
                except Exception:
                    pass
        by_customer[order["customer"]] = by_customer.get(order["customer"], 0) + total
    top = sorted(by_customer.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "lines": [split_row(line) for line in lines],
        "top_customers": [{"customer": c, "total": format_price(t)} for c, t in top],
        "skipped": skipped,
    }
