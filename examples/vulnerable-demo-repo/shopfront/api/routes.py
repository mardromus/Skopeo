"""HTTP request handlers. Every handler except ``login`` requires authentication."""

from shopfront.auth.middleware import issue_token, require_auth
from shopfront.auth.passwords import verify_password
from shopfront.db import get_connection, init_schema, load_seed
from shopfront.legacy import legacy_price_lookup
from shopfront.services.notifications import notify_customers
from shopfront.services.orders import list_orders_with_items
from shopfront.services.reports import build_sales_report

# Demo user store: username -> password digest
USERS = {"demo": "5f4dcc3b5aa765d61d8327deb882cf99"}


def _connection():
    conn = get_connection()
    init_schema(conn)
    load_seed(conn)
    return conn


def login(request: dict) -> dict:
    body = request.get("body", {})
    username, password = body.get("username", ""), body.get("password", "")
    digest = USERS.get(username)
    if digest is None or not verify_password(password, digest):
        return {"status": 401, "body": {"error": "invalid credentials"}}
    return {"status": 200, "body": {"token": issue_token(username)}}


@require_auth
def get_orders(request: dict) -> dict:
    return {"status": 200, "body": list_orders_with_items(_connection())}


@require_auth
def get_report(request: dict) -> dict:
    orders = list_orders_with_items(_connection())
    return {"status": 200, "body": build_sales_report(orders, request.get("query", {}))}


@require_auth
def get_price(request: dict) -> dict:
    sku = request.get("query", {}).get("sku", "")
    return {"status": 200, "body": {"sku": sku, "price": legacy_price_lookup(sku)}}


@require_auth
def post_notify(request: dict) -> dict:
    customers = request.get("body", {}).get("customers", [])
    sent = notify_customers(customers, request.get("body", {}).get("message", ""))
    return {"status": 202, "body": {"sent": sent}}


ROUTES = {
    ("POST", "/login"): login,
    ("GET", "/orders"): get_orders,
    ("GET", "/reports/sales"): get_report,
    ("GET", "/price"): get_price,
    ("POST", "/notify"): post_notify,
}
