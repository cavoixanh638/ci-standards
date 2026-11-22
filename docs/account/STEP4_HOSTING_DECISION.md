# Step 4 hosting decision - 2026-11-22

Scope: one HTTPS webhook receiver plus read-only repository discovery for `cavoixanh638`. No CI execution, account write access, merge, deploy, or paid service by default.

| Candidate | Strengths | Constraints | Decision |
| --- | --- | --- | --- |
| Cloudflare Workers Free + private D1 | Native HTTPS, free daily bounded quota, cron, no always-on owner machine; no GitHub Actions | JS/WebCrypto implementation needed; 10 ms CPU budget, 50 subrequests per invocation; owner must create CF account and hold private credentials | Preferred as a staged PoC; require real-runtime and quota acceptance |
| Always Free VM, e.g. Oracle | Existing Python/SQLite receiver could run unchanged with a private disk | Requires account eligibility, capacity/region, host patching, TLS, uptime/backup, and potential signup restrictions | Fallback only after owner review |
| Owner computer + trusted HTTPS proxy | Reuses Python receiver; complete physical control | Must stay powered and online, NAT/dynamic IP or tunnel complications, owner security burden | Not suitable for unattended always-on detection |

## Policy

- Free plan quota exhaustion must **stop service** rather than upgrade or charge. Check actual billing settings at the provider before activation; a local `max_additional_paid_usd=0` flag is not the provider's billing guarantee.
- Do not choose Railway/Render paid always-on plans automatically. Do not rely on time-limited free trial or credit card-funded compute.
- Public Git repository holds **only code, templates, schema and synthetic tests**. Actual private inventory belongs to an owner-managed D1 database.
- GitHub App requests `Metadata: Read-only` only. Event intake cannot build, merge or deploy.
- Worker starts inert (`MODE=dry_run`) and scheduled sync is commented out. Owner manual authorization is a separate deployment gate.

## External-source verification

Cloudflare (checked Nov 22, 2026) lists Workers Free ~100,000 requests/day, 10ms CPU/request, and 50 subrequests; D1 Free has 5 million rows read/day, 100,000 rows written/day, and free capacity caps. D1 free-tier overage causes query errors, not automatic paid usage. GitHub supports webhook HMAC-SHA256, installation tokens, and metadata-scoped access. These are *provider policy documents*, not evidence that the user's account is currently enrolled in Free.

References: https://developers.cloudflare.com/workers/platform/limits/ ; https://developers.cloudflare.com/d1/platform/pricing/ ; https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/ ; https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
