# Step 5 — offline, owner-controlled activation preflight

The Step 4 Cloudflare Worker/D1 remains **NOT DEPLOYED**. The owner has not yet supplied a live Cloudflare account session or confirmed GitHub App setup. Step 5 adds a **local advisory checklist**, not a runtime service or a deployment action.

1. Copy `examples/activation-evidence.example.json` to a **local ignored path** such as `private/activation-evidence.json`. Keep evidence private; never add credentials, PEM, repository inventory or token values.
2. Verify the Free plan, D1 remote migration/restore, dry-run HTTPS, real signed webhook/replay, Metadata-read-only installation, complete GitHub API pagination, quota/no paid use and emergency stop **in the owner's accounts**. Mark an item `true` only after manually observing it.
3. Run (offline; returns exit code **3** when any item is HOLD):

```sh
python3 tools/activation_preflight.py --policy config/account.defaults.json --evidence private/activation-evidence.json
python3 -m unittest discover -s tests -v
```

`READY_FOR_OWNER_REVIEW` means **all fields are self-attested**, not independently checked. It neither authorizes a deployment nor alters account settings. Activation is always a separate **manual** owner decision. Required repository permissions stay `Metadata: read`; CI/workflows, private-repo content access, Draft PR generation, merges and production deployments remain disabled. Do not enable the six-hour Cron while any evidence is HOLD.

**Rollback:** discard this Draft PR; no changes to running infrastructure or target repositories. If tests fail, keep `MODE=dry_run` and the GitHub App webhook disabled.

**Source/test checkpoint:** separate stacked Draft PR based on Step 4; Python syntax/unit tests and account policy must pass on its exact source; live Cloudflare + D1 + App + Billing acceptance remains `NOT_RUN` until owner connects the necessary services. No additional GitHub Actions usage is required for this offline tool.
