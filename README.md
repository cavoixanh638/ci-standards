# CI Standards - staged account-wide GitHub QA system

Central source of testing policies and a planned repository discovery service for `cavoixanh638`. **Not an active GitHub App; not deployed.** Work is divided into stacked Draft PRs so nothing automatically changes `main` or triggers GitHub Actions.

## Components

- `config/account.defaults.json`: `dry_run`, no automatic PR, workflow, merge, deploy or additional paid spend.
- `tools/`: conservative test selection, fingerprints/checkpoints, offline onboarding policy validation.
- `github_app/`: Step 3 Python + SQLite local read-only webhook detection prototype.
- **`cloudflare_worker/`: Step 4 Cloudflare Workers Free + D1 HTTPS candidate, with no active trigger or credentials.** Supports HMAC-authenticated webhook and periodic metadata-only reconciliation after owner activation.
- `tests/` and `cloudflare_worker/tests/`: local Python and Node.js/SQLite tests, respectively.
- `docs/account/STEP4_HOSTING_DECISION.md` and `docs/account/STEP4_CHECKPOINT.md`: hosting selection, safety and verification status.

## Test without cloud services

```sh
python3 -m unittest discover -s tests -v
python3 tools/validate_account_policy.py config/account.defaults.json
cd cloudflare_worker && npm test
```

## Deployment gate

The Worker is **inert by default** (`MODE=dry_run`, no active Cron Trigger). Do not deploy it, register an App, or change Billing on the user's behalf without the required Cloudflare account and explicit owner approval. Use a distinct owner-managed GitHub App with **Metadata: Read-only**; the existing ChatGPT GitHub connector is not the new App. See [`cloudflare_worker/README.md`](cloudflare_worker/README.md) for private setup steps.

**Always:** keep all Private repo inventories and credentials outside the Public Git repository; do not enable automated tests, writes or releases until each repository's required checks and triggers are reviewed. Never treat skipped or unexecuted tests as PASS.
