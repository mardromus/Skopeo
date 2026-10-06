"""Benchmark list_orders_with_items as the dataset grows.

Skopeo benchmark protocol: print exactly one JSON object on stdout with
``benchmark``, ``target`` and ``results`` (a list of {n, queries, seconds}).
"""

import json
import sys
import time

from shopfront.db import get_connection, init_schema
from shopfront.services.orders import list_orders_with_items

SIZES = (50, 500, 2000)


def populate(conn, n: int) -> None:
    conn.executemany(
        "INSERT INTO orders (id, customer, created_at) VALUES (?, ?, ?)",
        [(i, f"customer{i}@shop.com", "2026-01-01T00:00:00Z") for i in range(1, n + 1)],
    )
    conn.executemany(
        "INSERT INTO order_items (order_id, sku, quantity, unit_price_cents) VALUES (?, ?, ?, ?)",
        [(i, f"SKU-{k}", 1, 100 * k) for i in range(1, n + 1) for k in range(1, 4)],
    )


def measure(n: int) -> dict:
    conn = get_connection()
    init_schema(conn)
    populate(conn, n)
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    started = time.perf_counter()
    rows = list_orders_with_items(conn, limit=n)
    elapsed = time.perf_counter() - started
    conn.set_trace_callback(None)
    selects = sum(1 for s in statements if s.lstrip().upper().startswith("SELECT"))
    return {"n": n, "rows": len(rows), "queries": selects, "seconds": round(elapsed, 6)}


def main() -> None:
    results = [measure(n) for n in SIZES]
    payload = {
        "benchmark": "bench_orders",
        "target": "shopfront/services/orders.py::list_orders_with_items",
        "results": results,
    }
    if "--json" in sys.argv:
        print(json.dumps(payload))
    else:
        for r in results:
            print(f"n={r['n']:>5} queries={r['queries']:>5} seconds={r['seconds']:.4f}")


if __name__ == "__main__":
    main()
