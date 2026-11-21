"""GitHub App metadata-only reconciliation. No repository mutations or Actions.

JWT signer is an optional runtime dependency; offline tests use an injected transport.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

API = "https://api.github.com"
API_VERSION = "2026-03-10"


class ApiRejected(RuntimeError):
    pass


def request_json(method: str, path: str, authorization: str, data: dict | None = None) -> dict:
    if method not in ("GET", "POST") or not path.startswith("/") or ".." in path or "//" in path or "#" in path:
        raise ApiRejected("disallowed API request")
    encoded = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + path, data=encoded, method=method, headers={
        "Authorization": f"Bearer {authorization}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "cavoixanh638-ci-standards-dry-run",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status not in (200, 201):
                raise ApiRejected("unexpected GitHub API status")
            output = response.read(2000000)
    except urllib.error.HTTPError as exc:
        raise ApiRejected(f"GitHub API returned HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise ApiRejected("GitHub API unavailable") from None
    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ApiRejected("malformed GitHub API response") from exc
    if not isinstance(result, dict):
        raise ApiRejected("unexpected GitHub API JSON")
    return result


def app_jwt(app_id: int, private_key_path: Path, *, now: int | None = None) -> str:
    if type(app_id) is not int or app_id <= 0 or not private_key_path.is_absolute() or not private_key_path.is_file():
        raise ApiRejected("invalid app ID or private key location")
    try:
        import jwt  # PyJWT[crypto], only needed for online reconciliation
    except ImportError as exc:
        raise ApiRejected("install PyJWT[crypto] to use live GitHub App auth") from exc
    current = int(now if now is not None else time.time())
    return jwt.encode({"iat": current - 60, "exp": current + 480, "iss": str(app_id)},
                      private_key_path.read_text(encoding="utf-8"), algorithm="RS256")


def installation_token(app_id: int, installation_id: int, private_key_path: Path,
                       request: Callable = request_json) -> str:
    if type(installation_id) is not int or installation_id <= 0:
        raise ApiRejected("invalid installation ID")
    token = app_jwt(app_id, private_key_path)
    payload = request("POST", f"/app/installations/{installation_id}/access_tokens", token,
                      {"permissions": {"metadata": "read"}})
    result = payload.get("token")
    if not isinstance(result, str) or not result:
        raise ApiRejected("installation token missing")
    return result


def list_repositories(token: str, request: Callable = request_json, max_pages: int = 50) -> list[dict[str, Any]]:
    """Collect every page; incomplete/invalid lists never reach the state store."""
    if not token:
        raise ApiRejected("empty installation access token")
    all_rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        result = request("GET", f"/installation/repositories?per_page=100&page={page}", token)
        rows = result.get("repositories")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ApiRejected("invalid repository page")
        all_rows.extend(rows)
        if len(rows) < 100:
            claimed = result.get("total_count")
            if type(claimed) is int and claimed != len(all_rows):
                raise ApiRejected("inconsistent GitHub repository count")
            return all_rows
    raise ApiRejected("repository pagination cap reached; refuse partial sync")
