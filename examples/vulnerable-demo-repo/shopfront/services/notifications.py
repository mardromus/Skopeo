"""Customer notifications via the internal notification gateway."""

import requests

NOTIFY_URL = "https://notifications.internal.example/send"


def notify_customers(customers: list[dict], message: str) -> int:
    sent = 0
    for customer in customers:
        response = requests.post(
            NOTIFY_URL, json={"to": customer["email"], "body": message}, timeout=5
        )
        if response.ok:
            sent += 1
    return sent
