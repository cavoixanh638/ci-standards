# Owner setup: staged GitHub CI Standards

**Step 1 COMPLETE:** The owner created `cavoixanh638/ci-standards` (Public). Main has a minimal README.

**Step 2 CANDIDATE:** Draft PR #1 `feat/account-wide-qa-bootstrap-20261121` into main. Tools and account policy in `dry_run`; not merged.

**Step 3 CANDIDATE:** Stacked Draft PR #2 `feat/github-app-detector-step3-20261122` into Step 2. Python/SQLite read-only webhook detector; not deployed.

**Step 4 CANDIDATE:** Stacked Draft PR (see GitHub PR list) implementing `cloudflare_worker/` for Cloudflare Workers Free + D1. No Cloudflare App, D1, live GitHub App, webhook or cron has been provisioned by ChatGPT. The owner must choose/authorize the Cloudflare account, Free plan, D1 and GitHub App credentials. Read `cloudflare_worker/README.md` for the full private activation checklist. **Do not paste secrets or PEM files into ChatGPT.**

Future activation gates: real Cloudflare runtime tests, metadata-read-only GitHub App installation approved by owner, D1 private persistence/backup, signed webhook redelivery, free-usage audit, and emergency stop. No repository write permissions until separately approved.
