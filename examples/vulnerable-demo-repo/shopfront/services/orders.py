"""Order queries."""


def list_orders_with_items(conn, limit: int = 100) -> list[dict]:
    orders = conn.execute(
        "SELECT id, customer, created_at FROM orders ORDER BY id LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for order in orders:
        items = conn.execute(
            "SELECT sku, quantity, unit_price_cents FROM order_items WHERE order_id = ?",
            (order["id"],),
        ).fetchall()
        result.append(
            {
                "id": order["id"],
                "customer": order["customer"],
                "created_at": order["created_at"],
                "items": [dict(item) for item in items],
            }
        )
    return result
