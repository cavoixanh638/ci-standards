#!/usr/bin/env python3
"""Fail-closed validation for account policy. No network, no Actions, no writes."""
import argparse
import json
from pathlib import Path

REQUIRED = {
    "rollout": {
        "detect_current_repositories", "detect_future_repositories",
        "onboard_without_review", "create_pr_automatically", "require_owner_approval"
    },
    "automation": {
        "github_app_registered", "webhook_receiver_configured", "allow_repository_writes"
    },
    "ci": {
        "allow_workflow_execution", "allow_private_repo_execution",
        "allow_paid_runners", "allow_automatic_release", "allow_automatic_deploy",
        "allow_auto_merge", "use_local_tests_first",
        "reuse_requires_fingerprint_and_evidence", "preserve_required_checks",
        "fail_closed_on_unknown_change"
    }
}

class PolicyError(ValueError):
    pass


def validate(raw):
    if not isinstance(raw, dict):
        raise PolicyError("policy must be an object")
    if set(raw) != {"schema_version", "owner", "rollout", "automation", "ci", "test_tiers"}:
        raise PolicyError("unexpected or missing top-level fields")
    if raw["schema_version"] != "1.0" or raw["owner"] != "cavoixanh638":
        raise PolicyError("unexpected owner/schema")
    for block, fields in REQUIRED.items():
        entry = raw[block]
        allow = fields | ({"mode"} if block == "rollout" else {"max_additional_paid_usd"} if block == "ci" else set())
        if not isinstance(entry, dict) or set(entry) != allow:
            raise PolicyError(f"{block}: unexpected or missing fields")
        for key in fields:
            if type(entry[key]) is not bool:
                raise PolicyError(f"{block}.{key} must be boolean")
    if raw["rollout"]["mode"] not in ("dry_run", "proposal_only", "enabled"):
        raise PolicyError("invalid rollout mode")
    if type(raw["ci"]["max_additional_paid_usd"]) not in (int, float) or raw["ci"]["max_additional_paid_usd"] != 0:
        raise PolicyError("paid budget must stay at zero in this bootstrap")
    if raw["test_tiers"] != ["quick", "selective", "acceptance"]:
        raise PolicyError("invalid tiers")
    # No automatic mutation/run while application is absent or in dry-run mode.
    if raw["rollout"]["mode"] == "dry_run":
        gates = (
            ("rollout", "onboard_without_review"),
            ("rollout", "create_pr_automatically"),
            ("automation", "allow_repository_writes"),
            ("ci", "allow_workflow_execution"),
            ("ci", "allow_private_repo_execution"),
            ("ci", "allow_paid_runners"),
            ("ci", "allow_automatic_release"),
            ("ci", "allow_automatic_deploy"),
            ("ci", "allow_auto_merge")
        )
        for block, key in gates:
            if raw[block][key]:
                raise PolicyError(f"unsafe dry_run: {block}.{key}")
    if raw["ci"]["allow_paid_runners"]:
        raise PolicyError("paid runners are forbidden")
    if raw["ci"]["allow_automatic_release"] or raw["ci"]["allow_automatic_deploy"]:
        raise PolicyError("automatic release/deploy not approved")
    if not (raw["ci"]["preserve_required_checks"] and raw["ci"]["fail_closed_on_unknown_change"] and raw["ci"]["reuse_requires_fingerprint_and_evidence"]):
        raise PolicyError("security gates cannot be disabled")
    if not raw["rollout"]["require_owner_approval"]:
        raise PolicyError("owner approval is required")
    if raw["automation"]["allow_repository_writes"] and not (raw["automation"]["github_app_registered"] and raw["automation"]["webhook_receiver_configured"]):
        raise PolicyError("writes require registered app and verified receiver")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.policy.read_text(encoding="utf-8"))
        validate(data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"POLICY_REJECTED: {exc}\n")
    print("POLICY_VALID_DRY_RUN" if data["rollout"]["mode"] == "dry_run" else "POLICY_VALID_WITH_REVIEW_REQUIRED")

if __name__ == "__main__":
    main()
