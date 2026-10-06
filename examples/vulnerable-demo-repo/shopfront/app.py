"""Minimal WSGI entrypoint dispatching to ``shopfront.api.routes.ROUTES``."""

import json

from shopfront.api.routes import ROUTES


def create_app():
    def application(environ, start_response):
        key = (environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/"))
        handler = ROUTES.get(key)
        if handler is None:
            start_response("404 Not Found", [("Content-Type", "application/json")])
            return [b'{"error": "not found"}']
        headers = {"Authorization": environ.get("HTTP_AUTHORIZATION", "")}
        response = handler({"headers": headers, "query": {}, "body": {}})
        start_response(f"{response['status']} OK", [("Content-Type", "application/json")])
        return [json.dumps(response["body"]).encode("utf-8")]

    return application
