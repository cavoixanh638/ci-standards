"""Optional read-only periodic sync while webhook receiver is running.

A failure never deletes or replaces previously known repository inventory.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .controller import Store
from .github_api import installation_token, list_repositories


def sync_once(db_path: Path, owner: str, app_id: int, installation_id: int, private_key: Path,
              token_maker: Callable = installation_token,
              fetcher: Callable = list_repositories) -> int:
    token = token_maker(app_id, installation_id, private_key)
    records = fetcher(token)
    store = Store(db_path)
    try:
        return store.reconcile(records, owner)
    finally:
        store.close()


class ReadOnlySyncWorker:
    def __init__(self, db_path: Path, owner: str, app_id: int, installation_id: int,
                 key_path: Path, interval_seconds: int = 21600):
        if interval_seconds < 3600:
            raise ValueError("read-only sync interval must be at least one hour")
        self.db_path, self.owner, self.app_id = db_path, owner, app_id
        self.installation_id, self.key_path = installation_id, key_path
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True, name="ci-standards-readonly-sync")
        self.thread.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                sync_once(self.db_path, self.owner, self.app_id, self.installation_id, self.key_path)
            except Exception:
                # Fail closed: keep prior state. No exception detail/tokens/repo names in logs.
                print("READ_ONLY_SYNC_UNAVAILABLE", flush=True)
            if self.stop_event.wait(self.interval_seconds):
                break

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=15)
