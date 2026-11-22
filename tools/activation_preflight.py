#!/usr/bin/env python3
"""Offline, fail-closed owner readiness checklist. NEVER deploys or uses credentials."""
import argparse
import json
from pathlib import Path

from validate_account_policy import PolicyError, validate

GATES = (
    ('cloudflare_free_confirmed', 'Owner verified Workers Free and D1 Free billing/quota'),
    ('d1_private_ready', 'Private D1 migration and recovery drill verified'),
    ('worker_https_dry_run', 'HTTPS healthz works with MODE=dry_run'),
    ('webhook_disabled_in_dry_run', 'Webhook rejects ingestion while disabled'),
    ('github_app_metadata_only', 'Owner GitHub App requests Metadata: read only'),
    ('github_app_scope_reviewed', 'Installation repository scope reviewed by owner'),
    ('signed_delivery_verified', 'Real HMAC webhook and retry/replay tested'),
    ('github_pagination_verified', 'Live read-only paginated inventory reconciled'),
    ('quota_and_no_paid_spend_verified', 'Real free-tier limits and no new paid spend verified'),
    ('emergency_stop_verified', 'Disable webhook/cron and revert to dry_run tested'),
    ('owner_approved_readonly', 'Owner expressly approved read-only activation'),
)


def assess(policy, evidence):
    """Advisory only: self-attested checks never grant permission to deploy or write."""
    validate(policy)
    if policy['rollout']['mode'] != 'dry_run':
        raise PolicyError('preflight requires dry_run policy')
    if not isinstance(evidence, dict) or set(evidence) != {'schema_version', 'owner', 'checks'}:
        raise PolicyError('invalid evidence envelope')
    if evidence['schema_version'] != '1.0' or evidence['owner'] != policy['owner']:
        raise PolicyError('wrong evidence version or owner')
    checks = evidence['checks']
    names = {name for name, _ in GATES}
    if not isinstance(checks, dict) or set(checks) != names:
        raise PolicyError('missing or unexpected evidence checks')
    if any(type(value) is not bool for value in checks.values()):
        raise PolicyError('all evidence checks must be explicit booleans')
    outcomes = [{'id': name, 'description': description,
                 'status': 'ATTESTED' if checks[name] else 'HOLD'}
                for name, description in GATES]
    holds = sum(row['status'] == 'HOLD' for row in outcomes)
    return {
        'schema_version': '1.0', 'owner': policy['owner'],
        'readiness': 'READY_FOR_OWNER_REVIEW' if holds == 0 else 'HOLD',
        'unresolved_checks': holds, 'checks': outcomes,
        'evidence_origin': 'SELF_ATTESTED_NOT_INDEPENDENTLY_VERIFIED',
        'cloud_deploy_performed': False, 'repository_mutations_performed': 0,
        'github_actions_dispatched': 0, 'automatic_enable_allowed': False,
        'next_action': 'manual-owner-review-only' if holds == 0 else 'resolve-hold-checks-privately',
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--policy', type=Path, required=True)
    ap.add_argument('--evidence', type=Path, required=True,
                    help='PRIVATE local copy; do not commit or paste secrets')
    args = ap.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding='utf-8'))
        evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
        result = assess(policy, evidence)
    except (OSError, ValueError, PolicyError) as exc:
        ap.exit(2, f'PREFLIGHT_HOLD: {exc}\n')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['readiness'] == 'READY_FOR_OWNER_REVIEW' else 3)


if __name__ == '__main__':
    main()
