# Step 4: Cloudflare Workers Free + D1 read-only detector

**Status: reviewed implementation candidate. NOT DEPLOYED.** The repository contains no live Worker, D1 database, GitHub App, private key, installation token, or auto-run workflow. The previous Python/SQLite detector remains an offline/reference implementation; the Cloudflare Worker is an alternative runtime that uses Web Crypto and D1 rather than a persistent Python process.

## Why this runtime

- Cloudflare Workers provides a managed public HTTPS URL; no paid server or owner desktop kept online.
- D1 persists only repository names/IDs, visibility, lifecycle, webhook delivery hashes and timestamps in the **owner's private Cloudflare account**, not in GitHub.
- Workers Free currently allows 100,000 requests/day, 10ms CPU/request, 50 subrequests/invocation, and a limited number of scheduled triggers. D1 Free has daily row and storage limits that **block on exhaustion**, not automatic paid charging. The owner must confirm an actual Free account and no auto-upgrade; do not deploy to a Paid plan.
- Existing repository test suites and branch protection are not touched. There is no API to create PRs or dispatch Actions in this Worker.
- Default `MODE=dry_run` disables webhook ingestion and GitHub polling. One cron schedule is commented out.

## Local tests (no external API or account needed)

```sh
cd cloudflare_worker
npm test
npm run check
```

Tests use native Node.js v22 `node:sqlite` as a D1-compatible SQL test double; both HMAC WebCrypto and RSA JWT signing are exercised with *generated fixture keys*. The D1 migration SQL and transaction/rollback behavior are tested locally. No dependency install, no GitHub Actions minutes, and no Cloudflare charges are used for those tests.

## Owner setup (never paste secrets into ChatGPT)

1. Confirm that the Cloudflare account is on **Workers Free**, not Workers Paid; review quotas/spending limit and keep additional paid use at 0 USD. If a Free account is unavailable, **STOP**.
2. Prepare the Worker configuration locally (do not commit it):

   ```sh
   cd cloudflare_worker
   cp wrangler.example.toml wrangler.toml
   npx wrangler login
   npx wrangler d1 create ci-standards-private
   ```

   Copy the exact D1 `database_id` shown by Wrangler into the **local ignored** `wrangler.toml`. Keep `MODE="dry_run"` and keep the Cron Trigger commented.
3. Apply schema only to the intended private D1 database, then deploy the inert Worker:

   ```sh
   npx wrangler d1 migrations apply DB --remote
   npx wrangler deploy
   ```

   Verify `https://<your-worker>.<account>.workers.dev/healthz` reports `mode=dry_run`; `/webhook` must return 503, `/repos` must return 404. No real GitHub App should point to the Worker yet.
4. In GitHub, register an **owner-managed private GitHub App** in [Developer settings -> GitHub Apps](https://github.com/settings/apps/new). Repository permission: **Metadata: Read-only**. Subscribe only to `repository`; `installation` and `installation_repositories` are automatic. Do **not** request Contents/Actions/Administration/Pull requests write. Set the Webhook URL to the HTTPS Worker `/webhook` URL; keep delivery inactive until secrets and verification are complete. Install to `cavoixanh638` with **All repositories** only after reviewing the requested permissions. The existing ChatGPT GitHub app installation is not the new App.
5. Obtain App ID, installation ID, generated webhook secret and GitHub App RSA private key from your own GitHub settings. Store with `wrangler secret put` commands from your trusted machine only. **Never share the secret values or PEM through chat, issue, CI log or Git.** The Cloudflare Worker expects a PKCS#8 `-----BEGIN PRIVATE KEY-----` key; if GitHub provides PKCS#1, convert **locally** using OpenSSL first, with file permissions restricted:

   ```sh
   openssl pkcs8 -topk8 -nocrypt -in /secure/github-app-private.pem -out /secure/github-app-pkcs8.pem
   npx wrangler secret put GITHUB_WEBHOOK_SECRET
   npx wrangler secret put GITHUB_APP_ID
   npx wrangler secret put GITHUB_INSTALLATION_ID
   npx wrangler secret put GITHUB_PRIVATE_KEY < /secure/github-app-pkcs8.pem
   ```

   The three other `secret put` commands prompt for values privately; no values belong in shell history. The generated RSA private key must be protected and deleted securely from temporary locations. Do not place the original PEM in this Git repository.
6. Before activation, run a **genuine test delivery**, validate HMAC and D1 persistence in the Cloudflare dashboard, compare the privately held inventory with GitHub, and test an invalid signature (must reject) and a duplicate delivery (must dedupe). Do not use production private repository content for fixtures. Test the 10ms CPU allowance and D1 quotas in the real Worker runtime.
7. Only after acceptance, change `MODE="read_only"` in the local `wrangler.toml`, enable `[triggers] crons = ["0 */6 * * *"]`, redeploy manually, and activate the GitHub App webhook. Compare an initial fully paginated read-only reconciliation with the account inventory. Record evidence privately.

**DO NOT run the deploy commands from ChatGPT without owner Cloudflare access.** This repository only contains code/templates; the connected GitHub tool does not grant Cloudflare management access.

## Runtime contract

- `GET /healthz`: returns non-sensitive mode and claims, no repo counts or names.
- `POST /webhook`: HMAC-SHA256 verified on raw bytes, 512KiB max, strict JSON (no duplicate keys), owner + installation verification, durable delivery idempotency, repo lifecycle updates only to D1.
- Webhook events: `ping`, `repository`, `installation`, `installation_repositories`. Other events/methods/paths rejected.
- Cron every 6h (only after manual activation) authenticates as App using RS256 JWT, obtains a metadata-only installation token, pages through `/installation/repositories`, validates the complete snapshot, writes atomically, and preserves newer webhook events.
- `installation` suspend/delete makes all repos inaccessible; later repo events cannot re-enable it until unsuspend/create.
- No public listing of private repositories, no log of secrets/credentials, no code to write to other repos or run workflows.

## Failure modes, privacy and emergency off

- Invalid signature/identity -> 401 and **no** D1 mutation.
- Duplicate identical delivery -> 200; conflicting same delivery UUID -> 409.
- D1 unavailable -> 503; incomplete GitHub pagination or API denial -> keep previous snapshot.
- D1 quota exhaustion can prevent receipt persistence. GitHub may **not automatically redeliver** failed webhooks; reconcile snapshots periodically and use GitHub's delivery redelivery UI if needed.
- GitHub App suspension prevents cron sync and prevents further repo activation.
- Emergency stop: set `MODE=dry_run` and redeploy, disable App webhook or suspend/uninstall the App, rotate secrets, and disable Cron Trigger. Does not touch individual projects.
- D1 is an external persistence provider: repository metadata from Private repos leaves GitHub only after the owner consents and installs the new App. Inventory may contain confidential repository names; restrict Cloudflare account access.
- The Worker does **not** provide secure analytics/dashboard/API browsing of inventory. Any private status report requires a separate authenticated operator tool and explicit approval.

## Acceptance gates

1. Zero live GitHub Actions triggered by this rollout, no paid services, no merged PR or deployed app as part of code authoring.
2. Offline tests PASS; real Worker/D1/Webhook/API integration still **NOT_RUN** until credentials, domain and account are provisioned privately.
3. Verify real webhook delivery, redelivery, GitHub token scope, quota behavior, D1 recoverability, DNS/TLS, and log redaction before using in routine operations.
4. To propose PRs automatically in a future phase, a *separate policy review and permission upgrade* must be approved. Do not infer any write permission from Metadata: Read.

## References

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
