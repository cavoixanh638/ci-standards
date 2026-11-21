# Step 3 checkpoint — local GitHub App detector candidate

- Date: 2026-11-22 (Asia/Bangkok)
- Target: `cavoixanh638/ci-standards`; separate branch/stacked Draft PR on top of Step 2, no merge
- Change: `github_app/controller.py`, `github_app/github_api.py`, `github_app/background.py`, `github_app/server.py`, `github_app/cli.py`, `github_app/requirements.txt`, documentation, tests
- Scope: signed webhook intake, durable event idempotency, owner+installation checks, repository lifecycle, paginated metadata-only reconciliation, loopback HTTP, optional read-only periodic sync
- Source/test relationship: codebase baseline 51 PASS from Step 2; Step 3 added 47 offline tests = **98/98 PASS** before push (confirm final count after any changes)
- Tested on: isolated Python 3.13 environment; no private repository contents or GitHub App private key used
- Tests run: `python3 -m unittest discover -s tests -v`, `python3 -m compileall -q github_app tests`, policy validator
- Negative assertions: wrong HMAC/JSON/owner/installation/GUID/oversize rejected; failed pagination leaves prior state; HTTP `/admin/merge` does not exist
- GitHub App JWT against GitHub / real webhook deliveries: **NOT_RUN** (no registered App or HTTPS host)
- Billing/GitHub Actions: **NOT_RUN**, no Actions triggered by candidate alone; check live history after PR
- Production readiness: **HOLD**. Registration, TLS reverse proxy, durable private volume, key handling, rate limit and alerting require later verification
- No release, merge, force push, paid runner, workflow dispatch, repo write or secrets committed
- Rollback: close Draft PR or delete feature branch; Step 2 Draft PR and `main` unchanged
