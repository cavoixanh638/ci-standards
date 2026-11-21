"""Operator CLI: server, authoritative reconciliation, and private local summary.

No repository mutations, no workflow dispatch, no scheduled calls or GitHub write API.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .controller import EventRejected, Store
from .background import ReadOnlySyncWorker
from .github_api import ApiRejected, installation_token, list_repositories
from .server import serve


def main() -> None:
    p = argparse.ArgumentParser(description="GitHub App dry-run detector; NO repo writes")
    p.add_argument("command", choices=("serve", "reconcile", "status"))
    p.add_argument("--database", type=Path, required=True, help="PRIVATE persistent sqlite file (outside Git)")
    p.add_argument("--owner", default="cavoixanh638")
    p.add_argument("--installation-id", type=int)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--live", action="store_true", help="Opt in to READ-ONLY GitHub API synchronization")
    p.add_argument("--sync-hours", type=int, default=6, help="Minimum 1 hour, default 6")
    args = p.parse_args()
    if args.owner != "cavoixanh638":
        p.error("unexpected owner")
    if not args.database.is_absolute():
        p.error("database path must be absolute and outside repo")
    if args.command == "reconcile" and not args.live:
        p.error("reconcile requires explicit --live; never silently call GitHub")
    db = Store(args.database)
    try:
        if args.command == "status":
            print(json.dumps(db.summary(), indent=2, ensure_ascii=False))
        elif args.command == "serve":
            secret = os.environ.get("CI_APP_WEBHOOK_SECRET", "")
            if not secret or not args.installation_id:
                p.error("serve requires webhook secret and installation ID")
            worker = None
            if args.live:
                if args.sync_hours < 1:
                    p.error("synchronization interval must be at least 1 hour")
                app_id = int(os.environ["CI_APP_ID"])
                key_path = Path(os.environ["CI_APP_PRIVATE_KEY_PATH"])
                if not key_path.is_absolute() or not key_path.is_file():
                    p.error("configured private key is missing")
                worker = ReadOnlySyncWorker(args.database, args.owner, app_id,
                                            args.installation_id, key_path,
                                            interval_seconds=args.sync_hours * 3600)
            try:
                if worker:
                    worker.start()
                serve(args.host, args.port, db, secret, args.owner, args.installation_id)
            finally:
                if worker:
                    worker.stop()
        else:
            app_id = int(os.environ["CI_APP_ID"])
            key_path = Path(os.environ["CI_APP_PRIVATE_KEY_PATH"])
            token = installation_token(app_id, args.installation_id, key_path)
            rows = list_repositories(token)
            count = db.reconcile(rows, args.owner)
            print(json.dumps({"status": "reconciled", "repository_count": count,
                              "mode": "read-only inventory; no PR or Actions"}))
    except (EventRejected, ApiRejected, KeyError, ValueError) as ex:
        p.exit(2, f"CONTROLLER_REJECTED: {ex}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
