from shopfront.db import get_connection, init_schema, load_seed
from shopfront.services.orders import list_orders_with_items


def test_list_orders_returns_result():
    conn = get_connection()
    init_schema(conn)
    load_seed(conn)
    orders = list_orders_with_items(conn)
    assert orders is not None
