"""Verified, fail-closed GitHub App event intake. Never changes repository contents.

State is local/private SQLite; never commit the database into a public repository.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

MAX_PAYLOAD_BYTES = 524288
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EVENT_ACTIONS = {
    "ping": {None},
    "repository": {"created", "renamed", "deleted", "transferred", "archived", "unarchived", "privatized", "publicized"},
    "installation": {"created", "deleted", "suspend", "unsuspend"},
    "installation_repositories": {"added", "removed"},
}


class EventRejected(ValueError):
    """Invalid event, identity, signature or contradictory redelivery."""


def verify_signature(secret: str, raw: bytes, signature: str | None) -> None:
    if not isinstance(secret, str) or not secret:
        raise EventRejected("webhook secret is not configured")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise EventRejected("payload exceeds limit")
    if not isinstance(signature, str) or not re.fullmatch(r"sha256=[0-9a-fA-F]{64}", signature):
        raise EventRejected("missing or invalid SHA256 signature")
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature[7:].lower()):
        raise EventRejected("signature does not match")


def strict_json(raw: bytes) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise EventRejected("ambiguous duplicate JSON key")
            out[k] = v
        return out
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise EventRejected("invalid UTF8 JSON payload") from ex
    if not isinstance(result, dict):
        raise EventRejected("payload must be a JSON object")
    return result


def validate_delivery(guid: str | None) -> str:
    try:
        value = str(uuid.UUID(guid)) if isinstance(guid, str) else ""
    except ValueError as ex:
        raise EventRejected("invalid delivery ID") from ex
    if not value or value != guid.lower():
        raise EventRejected("invalid delivery ID")
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise EventRejected(f"invalid {label}")
    return value


def _repo(item: Any, owner: str) -> tuple[int, str, str]:
    if not isinstance(item, dict):
        raise EventRejected("invalid repository object")
    rid = _positive_int(item.get("id"), "repository id")
    full = item.get("full_name")
    if not isinstance(full, str) or not REPO_NAME.fullmatch(full):
        raise EventRejected("invalid repository full_name")
    if full.partition("/")[0].casefold() != owner.casefold():
        raise EventRejected("repository owner does not match installation")
    sub = item.get("owner")
    if sub is not None and (not isinstance(sub, dict) or str(sub.get("login", "")).casefold() != owner.casefold()):
        raise EventRejected("repository.owner mismatch")
    status = "archived" if item.get("archived") is True else "active"
    return rid, full, status


def parse_event(event: str | None, payload: dict[str, Any], expected_owner: str, expected_installation_id: int) -> list[tuple[int, str, str]]:
    """Return verified repository state transitions, never an executable task."""
    action = payload.get("action")
    if event not in EVENT_ACTIONS or action not in EVENT_ACTIONS[event]:
        raise EventRejected("unsupported event/action")
    if event == "ping":
        return []
    installation = payload.get("installation")
    if not isinstance(installation, dict) or _positive_int(installation.get("id"), "installation ID") != expected_installation_id:
        raise EventRejected("installation identity mismatch")
    account = installation.get("account")
    if not isinstance(account, dict) or str(account.get("login", "")).casefold() != expected_owner.casefold():
        raise EventRejected("installation account mismatch")
    if account.get("type") not in ("User", "Organization"):
        raise EventRejected("installation account type unknown")

    if event == "repository":
        rid, name, status = _repo(payload.get("repository"), expected_owner)
        if action in ("deleted", "transferred"):
            status = "inaccessible"
        return [(rid, name, status)]
    if event == "installation_repositories":
        added = payload.get("repositories_added", [])
        removed = payload.get("repositories_removed", [])
        if not isinstance(added, list) or not isinstance(removed, list):
            raise EventRejected("invalid repository lists")
        if action == "added" and not added and not removed:
            raise EventRejected("empty installation repository change")
        result = [ _repo(obj, expected_owner) for obj in added]
        result.extend((rid, name, "inaccessible") for rid, name, _ in (_repo(obj, expected_owner) for obj in removed))
        return result
    if event == "installation":
        if action == "created":
            raw = payload.get("repositories", [])
            if not isinstance(raw, list):
                raise EventRejected("invalid initial repository list")
            return [_repo(obj, expected_owner) for obj in raw]
        return []  # deleted/suspend applied transactionally to every known repository
    raise EventRejected("unsupported event")


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            parent = Path(self.path).parent
            if not parent.is_dir():
                raise EventRejected("database parent directory must already exist")
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS deliveries (
                guid TEXT PRIMARY KEY, content_hash TEXT NOT NULL, received_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS repositories (
                repo_id INTEGER PRIMARY KEY, full_name TEXT NOT NULL, state TEXT NOT NULL,
                source TEXT NOT NULL, observed_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
        """)

    def close(self) -> None:
        self.db.close()

    def apply_webhook(self, guid: str, event: str, payload: dict[str, Any], raw: bytes, transitions: list[tuple[int, str, str]]) -> str:
        fingerprint = hashlib.sha256(raw).hexdigest()
        now = int(time.time())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self.db.execute("SELECT content_hash FROM deliveries WHERE guid=?", (guid,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise EventRejected("delivery GUID reused with different payload")
                self.db.execute("COMMIT")
                return "duplicate"
            action = payload.get("action")
            if event == "installation" and action in ("deleted", "suspend"):
                self.db.execute("UPDATE repositories SET state='inaccessible', source=?, observed_at=?", (f"installation.{action}", now))
                self.db.execute("INSERT INTO app_state(key,value) VALUES('installation','inactive') ON CONFLICT(key) DO UPDATE SET value='inactive'")
            if event == "installation" and action in ("created", "unsuspend"):
                self.db.execute("INSERT INTO app_state(key,value) VALUES('installation','needs-reconcile') ON CONFLICT(key) DO UPDATE SET value='needs-reconcile'")
            for rid, full, state in transitions:
                self.db.execute("""INSERT INTO repositories(repo_id,full_name,state,source,observed_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,
                    state=excluded.state,source=excluded.source,observed_at=excluded.observed_at""",
                    (rid, full, state, f"webhook:{event}.{action}", now))
            self.db.execute("INSERT INTO deliveries VALUES(?,?,?)", (guid, fingerprint, now))
            self.db.execute("COMMIT")
            return "accepted"
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def reconcile(self, rows: list[dict[str, Any]], owner: str) -> int:
        """Authoritative snapshot. The caller MUST fetch every API page first."""
        transitions = [_repo(row, owner) for row in rows]
        if len({rid for rid, _, _ in transitions}) != len(transitions):
            raise EventRejected("duplicate repository id in snapshot")
        now = int(time.time())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("UPDATE repositories SET state='inaccessible',source='reconcile:removed',observed_at=?", (now,))
            for rid, full, state in transitions:
                self.db.execute("""INSERT INTO repositories(repo_id,full_name,state,source,observed_at)
                    VALUES(?,?,?,?,?) ON CONFLICT(repo_id) DO UPDATE SET full_name=excluded.full_name,
                    state=excluded.state,source=excluded.source,observed_at=excluded.observed_at""", (rid, full, state, "reconcile:full", now))
            self.db.execute("INSERT INTO app_state(key,value) VALUES('installation','active') ON CONFLICT(key) DO UPDATE SET value='active'")
            self.db.execute("COMMIT")
            return len(transitions)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def summary(self) -> dict[str, Any]:
        states = dict(self.db.execute("SELECT state, COUNT(*) FROM repositories GROUP BY state"))
        return {"total_known": sum(states.values()), "states": states,
                "deliveries_recorded": self.db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0],
                "installation": (self.db.execute("SELECT value FROM app_state WHERE key='installation'").fetchone() or ["unknown"])[0]}


def intake(store: Store, *, secret: str, event: str | None, guid: str | None,
           signature: str | None, raw: bytes, owner: str, installation_id: int) -> str:
    """Check signature *before* decoding, validating identity or touching SQLite."""
    verify_signature(secret, raw, signature)
    key = validate_delivery(guid)
    payload = strict_json(raw)
    transitions = parse_event(event, payload, owner, installation_id)
    return store.apply_webhook(key, event, payload, raw, transitions)
