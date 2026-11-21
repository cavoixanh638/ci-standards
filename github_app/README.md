# GitHub App repository detector (Step 3, safe dry-run)

This is a **working local, read-only control-plane prototype**. It receives signed webhooks, records an installation-scoped repository inventory in a PRIVATE SQLite file, and optionally reconciles GitHub installation repositories using a metadata-only token. It does not create PRs, edit source/workflows, run Actions, change Billing, merge, or deploy.

## Offline verification (no GitHub access)

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q github_app tests
```

## Operation, once a GitHub App and HTTPS endpoint are approved

- Register an owner-managed **private** GitHub App with **Metadata: read** permission and the **repository** event. The `installation` and `installation_repositories` events are sent automatically to Apps.
- Install with **All repositories** only after confirming access scope. A separate ChatGPT GitHub connection is *not* this App.
- Host a dedicated HTTPS reverse proxy with a trusted certificate; forward only `/webhook` to the receiver on `127.0.0.1:8765`. This application deliberately refuses binding `0.0.0.0`.
- Store webhook secret, App private key, and SQLite under private persistent storage *outside Git*, backed up securely. Do not paste secrets into chat or commit.
- Supply `CI_APP_WEBHOOK_SECRET`, `CI_APP_ID`, `CI_APP_PRIVATE_KEY_PATH` from the host's secret manager and use the installed App's **installation ID**.
- From repo root, start the detector locally (only webhook intake, no external API calls):

```sh
python3 -m github_app.cli serve --database /private/ci-standards/state.sqlite --installation-id INSTALLATION_ID
```

- To enable **read-only** initial inventory and periodic recovery (every six hours by default), install the optional auth dependency and explicitly use `--live`:

```sh
python3 -m pip install -r github_app/requirements.txt
python3 -m github_app.cli serve --database /private/ci-standards/state.sqlite --installation-id INSTALLATION_ID --live --sync-hours 6
```

- To reconcile once rather than start a service:

```sh
python3 -m github_app.cli reconcile --database /private/ci-standards/state.sqlite --installation-id INSTALLATION_ID --live
python3 -m github_app.cli status --database /private/ci-standards/state.sqlite
```

The `/healthz` endpoint returns only the mode, never repository names, tokens or payloads. Webhook delivery IDs are durably deduplicated and the request body is never stored. If GitHub returns incomplete pagination, a bad installation identity, or an invalid signature, the operation fails closed without replacing inventory.

**Important:** This prototype is NOT an always-on service until you register/install the App and deploy an HTTPS host. It does not automatically create onboarding PRs; the next phase must implement draft-PR proposals behind reviewed opt-in policy. Never enable the old PR `main` triggers or change required checks automatically.
