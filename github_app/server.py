"""Minimal HTTP receiver. Bind loopback; use HTTPS reverse proxy for real webhook delivery."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .controller import EventRejected, MAX_PAYLOAD_BYTES, Store, intake


def make_handler(store: Store, secret: str, owner: str, installation_id: int):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status: int, value: dict) -> None:
            body = (json.dumps(value) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self.send_json(200, {"ok": True, "mode": "dry_run"})
            else:
                self.send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/webhook":
                self.send_json(404, {"error": "not_found"})
                return
            if self.headers.get("Transfer-Encoding"):
                self.send_json(400, {"error": "chunked_not_accepted"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_PAYLOAD_BYTES:
                self.send_json(413, {"error": "payload_size_rejected"})
                return
            if self.headers.get_content_type() != "application/json":
                self.send_json(415, {"error": "content_type_rejected"})
                return
            try:
                result = intake(store, secret=secret, event=self.headers.get("X-GitHub-Event"),
                                guid=self.headers.get("X-GitHub-Delivery"),
                                signature=self.headers.get("X-Hub-Signature-256"),
                                raw=self.rfile.read(length), owner=owner, installation_id=installation_id)
            except EventRejected:
                self.send_json(401, {"error": "webhook_rejected"})
                return
            self.send_json(200 if result == "duplicate" else 202, {"status": result, "mode": "dry_run"})

        def log_message(self, format_string, *args) -> None:
            # Never log payloads, private repository names, secrets or request headers.
            pass
    return Handler


def serve(host: str, port: int, store: Store, secret: str, owner: str, installation_id: int) -> None:
    if host not in ("127.0.0.1", "localhost"):
        raise EventRejected("bind loopback only; terminate HTTPS at a trusted reverse proxy")
    if not secret or type(installation_id) is not int or installation_id <= 0:
        raise EventRejected("webhook secret and installation ID required")
    httpd = HTTPServer((host, port), make_handler(store, secret, owner, installation_id))
    try:
        httpd.serve_forever(poll_interval=0.25)
    finally:
        httpd.server_close()
