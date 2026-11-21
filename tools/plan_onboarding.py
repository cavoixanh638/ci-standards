#!/usr/bin/env python3
"""Offline inventory -> onboarding plan. Emits JSON; never calls GitHub or executes tests."""
import argparse
import json
from pathlib import Path
from validate_account_policy import validate, PolicyError


def infer_tech(paths):
    items = set(paths)
    if "pubspec.yaml" in items:
        return "flutter"
    if "compose.yaml" in items or "docker-compose.yml" in items:
        return "docker-stack"
    if "package.json" in items:
        return "node"
    if "pyproject.toml" in items or "requirements.txt" in items:
        return "python"
    if "index.html" in items:
        return "static-web"
    return "unknown-review-required"


def plan(policy, inventory):
    validate(policy)
    if not isinstance(inventory, dict) or inventory.get("schema_version") != "1.0" or inventory.get("owner") != policy["owner"]:
        raise PolicyError("invalid inventory schema or owner")
    repos = inventory.get("repositories")
    if not isinstance(repos, list) or len(repos) > 500:
        raise PolicyError("invalid repository inventory")
    seen = set()
    result = []
    for repo in repos:
        if not isinstance(repo, dict) or set(repo) != {"name", "visibility", "default_branch", "root_files"}:
            raise PolicyError("invalid repository entry")
        full = repo["name"]
        if not isinstance(full, str) or not full.startswith(policy["owner"] + "/") or full in seen:
            raise PolicyError("owner mismatch, invalid or duplicated repository")
        seen.add(full)
        if repo["visibility"] not in ("public", "private"):
            raise PolicyError("unknown visibility")
        if not isinstance(repo["default_branch"], str) or not repo["default_branch"]:
            raise PolicyError("invalid default branch")
        if repo["root_files"] is not None and (not isinstance(repo["root_files"], list) or not all(isinstance(x, str) for x in repo["root_files"])):
            raise PolicyError("invalid root_files")
        result.append({
            "repository": full,
            "visibility": repo["visibility"],
            "detected_technology": infer_tech(repo["root_files"]) if repo["root_files"] is not None else "unknown-uninspected",
            "root_files_inspected": repo["root_files"] is not None,
            "next_action": "review-and-propose-draft-pr",
            "tests_scheduled": 0,
            "mutations_performed": 0,
            "requires_owner_approval": True,
            "release_or_deploy_allowed": False,
            "notes": "No code or workflow changes. Analyze existing required checks and trigger cost before enrollment."
        })
    return {"schema_version": "1.0", "owner": policy["owner"], "mode": policy["rollout"]["mode"], "repositories": sorted(result, key=lambda x: x["repository"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--inventory", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        p = json.loads(args.policy.read_text(encoding="utf-8"))
        r = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = json.dumps(plan(p, r), indent=2, ensure_ascii=False) + "\n"
    except (ValueError, OSError) as exc:
        ap.exit(2, f"ONBOARDING_REJECTED: {exc}\n")
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")

if __name__ == "__main__":
    main()
