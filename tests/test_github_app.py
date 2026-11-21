"""Offline security, event and read-only GitHub App regression tests."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from github_app.controller import (
    EventRejected, Store, intake, parse_event, strict_json, verify_signature,
)
from github_app.github_api import ApiRejected, list_repositories, request_json, installation_token, app_jwt
from github_app.server import serve

OWNER = "cavoixanh638"
INSTALL_ID = 54123
SECRET = "test-only-webhook-key-please-never-use-in-production"


def signature(raw):
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def installation():
    return {"id": INSTALL_ID, "account": {"login": OWNER, "type": "User"}}


def repository(rid=1, name="alpha", archived=False):
    return {"id": rid, "full_name": OWNER + "/" + name, "archived": archived,
            "owner": {"login": OWNER}}


def payload(event="repository", action="created", **overrides):
    data = {"action": action, "installation": installation(), "repository": repository()}
    if event == "installation_repositories":
        data.pop("repository")
        data.update({"repositories_added": [repository()], "repositories_removed": []})
    if event == "installation":
        data.pop("repository")
        data["repositories"] = [repository()]
    data.update(overrides)
    return json.dumps(data, separators=(",", ":")).encode()


class WebhookAuthTests(unittest.TestCase):
    def test_accepts_correct_hmac(self):
        verify_signature(SECRET, b"test", signature(b"test"))

    def test_rejects_tampered_body(self):
        with self.assertRaises(EventRejected):
            verify_signature(SECRET, b"changed", signature(b"test"))

    def test_rejects_old_sha1_header(self):
        with self.assertRaises(EventRejected):
            verify_signature(SECRET, b"test", "sha1=" + "a" * 40)

    def test_rejects_missing_signature(self):
        with self.assertRaises(EventRejected):
            verify_signature(SECRET, b"test", None)

    def test_rejects_missing_secret(self):
        with self.assertRaises(EventRejected):
            verify_signature("", b"test", signature(b"test"))

    def test_rejects_too_large(self):
        with self.assertRaises(EventRejected):
            verify_signature(SECRET, b"x" * 524289, signature(b"x" * 524289))

    def test_rejects_duplicate_json_key(self):
        with self.assertRaises(EventRejected):
            strict_json(b'{"action":"created","action":"deleted"}')

    def test_rejects_bad_json(self):
        for raw in (b"not-json", b"[]", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(EventRejected):
                strict_json(raw)


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.db")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def send(self, raw, event="repository", guid=None, sig=None):
        return intake(self.store, secret=SECRET, raw=raw, event=event, guid=guid or str(uuid.uuid4()),
                      signature=sig or signature(raw), owner=OWNER, installation_id=INSTALL_ID)

    def test_create_is_inventory_only(self):
        self.assertEqual(self.send(payload()), "accepted")
        self.assertEqual(self.store.summary()["states"], {"active": 1})

    def test_replay_is_idempotent(self):
        raw = payload()
        guid = str(uuid.uuid4())
        self.assertEqual(self.send(raw, guid=guid), "accepted")
        self.assertEqual(self.send(raw, guid=guid), "duplicate")
        self.assertEqual(self.store.summary()["deliveries_recorded"], 1)

    def test_guid_collision_with_different_content_rejected(self):
        guid = str(uuid.uuid4())
        self.send(payload(), guid=guid)
        with self.assertRaises(EventRejected):
            self.send(payload(action="archived"), guid=guid)
        self.assertEqual(self.store.summary()["deliveries_recorded"], 1)

    def test_rejects_forged_installation(self):
        bad = installation()
        bad["id"] = 777
        with self.assertRaises(EventRejected):
            self.send(payload(installation=bad))
        self.assertEqual(self.store.summary()["total_known"], 0)

    def test_rejects_other_account(self):
        bad = installation()
        bad["account"]["login"] = "unauthorized-user"
        with self.assertRaises(EventRejected):
            self.send(payload(installation=bad))

    def test_rejects_other_repo_owner(self):
        wrong = repository()
        wrong["full_name"] = "someone-else/alpha"
        with self.assertRaises(EventRejected):
            self.send(payload(repository=wrong))

    def test_rejects_mismatched_repo_owner_field(self):
        wrong = repository()
        wrong["owner"] = {"login": "other"}
        with self.assertRaises(EventRejected):
            self.send(payload(repository=wrong))

    def test_rejects_unrecognized_event(self):
        with self.assertRaises(EventRejected):
            self.send(payload(), event="workflow_run")

    def test_rejects_bad_guid(self):
        with self.assertRaises(EventRejected):
            self.send(payload(), guid="not-uuid")

    def test_signature_checked_before_json(self):
        with self.assertRaises(EventRejected):
            self.send(b"{not json", sig=signature(b"different"))
        self.assertEqual(self.store.summary()["deliveries_recorded"], 0)

    def test_repository_renamed_by_id(self):
        self.send(payload())
        self.send(payload(action="renamed", repository=repository(name="new-name")))
        row = self.store.db.execute("SELECT full_name FROM repositories WHERE repo_id=1").fetchone()
        self.assertEqual(row[0], OWNER + "/new-name")

    def test_repository_deleted_is_inaccessible(self):
        self.send(payload())
        self.send(payload(action="deleted"))
        self.assertEqual(self.store.summary()["states"], {"inaccessible": 1})

    def test_installation_created_proposes_initial_inventory(self):
        self.send(payload(event="installation", action="created", repositories=[repository(7, "beta")]), event="installation")
        self.assertEqual(self.store.summary()["installation"], "needs-reconcile")
        self.assertEqual(self.store.summary()["states"], {"active": 1})

    def test_installation_suspended_removes_access(self):
        self.send(payload())
        self.send(payload(event="installation", action="suspend"), event="installation")
        self.assertEqual(self.store.summary()["states"], {"inaccessible": 1})
        self.assertEqual(self.store.summary()["installation"], "inactive")

    def test_installation_added_and_removed(self):
        self.send(payload(event="installation_repositories", action="added"), event="installation_repositories")
        self.assertEqual(self.store.summary()["states"], {"active": 1})
        self.send(payload(event="installation_repositories", action="removed", repositories_added=[],
                          repositories_removed=[repository()]), event="installation_repositories")
        self.assertEqual(self.store.summary()["states"], {"inaccessible": 1})

    def test_ping_is_signed_but_no_repo_write(self):
        self.assertEqual(self.send(b'{"zen":"ok"}', event="ping"), "accepted")
        self.assertEqual(self.store.summary()["total_known"], 0)

    def test_store_persists_between_processes(self):
        self.send(payload())
        other = Store(Path(self.temp.name) / "state.db")
        self.assertEqual(other.summary()["total_known"], 1)
        other.close()

    def test_reconcile_updates_and_marks_missing_without_actions(self):
        self.send(payload())
        self.assertEqual(self.store.reconcile([repository(4, "new")], OWNER), 1)
        self.assertEqual(self.store.summary()["states"], {"inaccessible": 1, "active": 1})

    def test_reconcile_owner_mismatch_is_atomic(self):
        self.send(payload())
        with self.assertRaises(EventRejected):
            self.store.reconcile([repository(4, "new"), {"id": 19, "full_name": "elsewhere/forbidden"}], OWNER)
        self.assertEqual(self.store.summary()["states"], {"active": 1})

    def test_reconcile_rejects_duplicate_repo_id(self):
        with self.assertRaises(EventRejected):
            self.store.reconcile([repository(), repository()], OWNER)

    def test_installation_created_invalid_list_is_atomic(self):
        with self.assertRaises(EventRejected):
            self.send(payload(event="installation", action="created", repositories=[repository(),
                                                                                      {"id": 2, "full_name": "other/repo"}]), event="installation")
        self.assertEqual(self.store.summary()["total_known"], 0)


class GithubApiTests(unittest.TestCase):
    def test_one_page_metadata_only(self):
        calls = []
        def fake(method, path, token):
            calls.append((method, path, token))
            return {"repositories": [repository()], "total_count": 1}
        self.assertEqual(len(list_repositories("not-a-real-token", request=fake)), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "GET")

    def test_multiple_pages(self):
        calls = []
        def fake(method, path, token):
            calls.append(path)
            if path.endswith("&page=1"):
                return {"repositories": [repository(i + 1, f"repo{i}") for i in range(100)], "total_count": 102}
            return {"repositories": [repository(101, "repo100"), repository(102, "repo101")], "total_count": 102}
        self.assertEqual(len(list_repositories("fake", request=fake)), 102)
        self.assertEqual(len(calls), 2)

    def test_incomplete_count_fails_closed(self):
        with self.assertRaises(ApiRejected):
            list_repositories("fake", request=lambda *_: {"repositories": [], "total_count": 19})

    def test_full_pages_cap_fails_closed(self):
        with self.assertRaises(ApiRejected):
            list_repositories("fake", request=lambda *_: {"repositories": [repository(i + 1, f"r{i}") for i in range(100)]}, max_pages=2)

    def test_reject_unbounded_or_user_url(self):
        for url in ("https://evil.invalid/", "/../private", "//example.com", "/foo#bar"):
            with self.subTest(url=url), self.assertRaises(ApiRejected):
                request_json("GET", url, "fake")

    def test_missing_private_key_never_generates_token(self):
        with self.assertRaises(ApiRejected):
            app_jwt(55, Path("relative.pem"))

    def test_invalid_installation_id(self):
        with self.assertRaises(ApiRejected):
            installation_token(123, -1, Path("/tmp/missing.pem"))

    def test_missing_token_from_endpoint_fails(self):
        with patch("github_app.github_api.app_jwt", return_value="fake-jwt"):
            with self.assertRaises(ApiRejected):
                installation_token(42, 43, Path("/missing/key"), request=lambda *_: {})

    def test_read_only_permissions_requested(self):
        called = []
        with patch("github_app.github_api.app_jwt", return_value="fake-jwt"):
            token = installation_token(42, 43, Path("/missing/key"),
                  request=lambda *args: (called.append(args) or {"token": "fake-token"}))
        self.assertEqual(token, "fake-token")
        self.assertEqual(called[0][3], {"permissions": {"metadata": "read"}})

    def test_server_requires_loopback(self):
        with self.assertRaises(EventRejected):
            serve("0.0.0.0", 0, Store(":memory:"), SECRET, OWNER, INSTALL_ID)


if __name__ == "__main__":
    unittest.main()
