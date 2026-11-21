"""Actual local HTTP webhook integration; no network requests to GitHub."""
import hashlib
import hmac
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from github_app.background import ReadOnlySyncWorker, sync_once
from github_app.controller import Store

ROOT = Path(__file__).resolve().parent.parent
SECRET = "local-only-hmac-test-secret"


def port_available():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.port = port_available()
        self.dbpath = Path(self.temp.name) / "state.sqlite"
        env = dict(os.environ, CI_APP_WEBHOOK_SECRET=SECRET)
        self.proc = subprocess.Popen([sys.executable, "-m", "github_app.cli", "serve", "--database",
                                      str(self.dbpath), "--installation-id", "987", "--port", str(self.port)],
                                     env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=0.5)
                conn.request("GET", "/healthz")
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                conn.close()
                break
            except (OSError, http.client.HTTPException):
                time.sleep(0.025)
        else:
            self.fail("local HTTP receiver not ready")

    def tearDown(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.temp.cleanup()

    def send(self, body, event="repository", signature=None, guid=None, ctype="application/json"):
        sign = signature or ("sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest())
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("POST", "/webhook", body, headers={"X-Hub-Signature-256": sign,
            "X-GitHub-Event": event, "X-GitHub-Delivery": guid or str(uuid.uuid4()), "Content-Type": ctype})
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def sample(self):
        return json.dumps({"action": "created", "installation": {"id": 987,
               "account": {"login": "cavoixanh638", "type": "User"}},
               "repository": {"id": 123, "full_name": "cavoixanh638/demo-repository"}}).encode()

    def test_post_valid_then_replay(self):
        body, guid = self.sample(), str(uuid.uuid4())
        self.assertEqual(self.send(body, guid=guid)[0], 202)
        self.assertEqual(self.send(body, guid=guid)[0], 200)
        state = Store(self.dbpath)
        self.assertEqual(state.summary()["states"], {"active": 1})
        self.assertEqual(state.summary()["deliveries_recorded"], 1)
        state.close()

    def test_post_unsigned_rejected(self):
        status, _ = self.send(self.sample(), signature="sha256=" + "0" * 64)
        self.assertEqual(status, 401)

    def test_post_wrong_type_rejected(self):
        status, _ = self.send(self.sample(), ctype="text/plain")
        self.assertEqual(status, 415)

    def test_post_oversized_rejected(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.putrequest("POST", "/webhook")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", "524289")
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 413)
        conn.close()

    def test_no_management_endpoint(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("POST", "/admin/merge", b"{}")
        self.assertEqual(conn.getresponse().status, 404)
        conn.close()


class PeriodicSyncTests(unittest.TestCase):
    def test_sync_once_uses_injected_readonly_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "state.db"
            called = []
            def token_maker(app_id, install_id, path):
                called.append((app_id, install_id, path))
                return "fake-token"
            def fetcher(token):
                self.assertEqual(token, "fake-token")
                return [{"id": 888, "full_name": "cavoixanh638/new-project"}]
            self.assertEqual(sync_once(dbpath, "cavoixanh638", 17, 18, Path("/no/key"),
                                       token_maker=token_maker, fetcher=fetcher), 1)
            self.assertEqual(called[0][:2], (17, 18))
            state = Store(dbpath)
            self.assertEqual(state.summary()["total_known"], 1)
            state.close()

    def test_sync_requires_safe_interval(self):
        with self.assertRaises(ValueError):
            ReadOnlySyncWorker(Path("/tmp/nonexistent"), "cavoixanh638", 1, 2, Path("/no/key"), 30)

    def test_sync_failed_fetch_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as temp:
            dbpath = Path(temp) / "state.db"
            state = Store(dbpath)
            state.reconcile([{"id": 100, "full_name": "cavoixanh638/old"}], "cavoixanh638")
            state.close()
            def raises(token):
                raise RuntimeError("offline test failure")
            with self.assertRaises(RuntimeError):
                sync_once(dbpath, "cavoixanh638", 1, 2, Path("/no/key"),
                          token_maker=lambda *_: "fake", fetcher=raises)
            state = Store(dbpath)
            self.assertEqual(state.summary()["states"], {"active": 1})
            state.close()


if __name__ == "__main__":
    unittest.main()
