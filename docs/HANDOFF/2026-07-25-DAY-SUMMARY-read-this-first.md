# Handoff — 2026-07-25 — Day summary (READ THIS FIRST)

Consolidated close-of-day handoff. **Start here**, then open whichever detailed handoff below
matters for what you're picking up.

| Detailed handoff | Covers |
| --- | --- |
| `2026-07-25-status-audit-and-planner-fixtures.md` | Status audit, prod reality-check, green test suite, admin user suspension |
| `2026-07-25-milestone-C-request-to-quote.md` | Milestone C — parties request-to-quote |
| `2026-07-25-mobile-nav-console-manuals.md` | Mobile tab bar, console drawers, console at phone width, the manuals |

**State at close:** `main` = `e833d45`, local and origin in sync, working tree clean.
Everything built today is **merged and deployed to production**. All local dev services are
**stopped** (§7). Production is **untouched and still serving**.

---

## 1. What changed today

Four pushes, all live:

| # | What | Where |
| --- | --- | --- |
| PR #21 | Green test suite · admin **user suspension** · party-planner polish | merged, deployed |
| PR #22 | **Milestone C** — parties request-to-quote (closed the ADR-0006 gate) | merged, deployed |
| PR #23 | Mobile **bottom tab bar** · provider/admin console **drawer fix** | merged, deployed |
| `cb6d287` | Console **pages at phone width** | pushed to main, deployed |
| `51075cc`+`ef4860d` | `docs/manuals/` — user, provider, admin manuals | pushed (docs, no deploy) |
| `e833d45` | `seed_accounts.py` + afternoon handoff | pushed (no deploy) |

The day started with a stale picture: the last handoff was six days and **ten merged PRs**
old, and it claimed its own work was unmerged. If a handoff ever looks that stale again,
verify against `git log --first-parent` before trusting it.

### The headline

**The ADR-0006 active gate is closed.** Milestones A, B, C and D are all complete. There is
**no active gate** right now — see §5.

---

## 2. Production: what's real, what isn't

`https://kidspots.store` — live, healthy, serving request-time SSR.

| Thing | State |
| --- | --- |
| Site + API | Live. `/` 200, api healthy, SSR rendering |
| Migrations | At `61452b91bbf6` |
| **Payments** | **`FakeGateway`** — `/api/v1/payments/config` returns `{"live":false}` |
| **Email** | Not configured — `SmtpEmailGateway` exists but has no credentials |
| `party_quotes` flag | **OFF** |
| `party_planner` flag | **OFF** |
| Backups | Manual `pg_dump` per deploy (`~/juggle-predeploy-*.sql.gz` on the VM) |

> ### ⚠️ The one thing that would hurt
>
> Production runs the **FakeGateway**. A real parent completing checkout on kidspots.store
> right now gets a **confirmed booking and an accrued provider payout for money that was
> never collected**. The site is publicly reachable and now has working login accounts (§4).
> Either add Stripe keys or gate checkout before anyone finds it.

---

## 3. Restarting the environment

Ports are non-default because other apps occupy 8000/5432 on this machine:

```bash
make db                                                  # Postgres/PostGIS on :5433
cd apps/api && uv run uvicorn juggle.main:app --reload --port 8001
cd apps/web && VITE_API_TARGET=http://localhost:8001 npm run dev    # :9000
cd apps/api && uv run python -m juggle.worker --loop     # optional, see the trap in §6
```

Sanity: `curl localhost:8001/health`.

Deploy: `./scripts/deploy.sh --backup --iap` (see §6 for why `--iap`).

---

## 4. Seeded accounts

`apps/api/scripts/seed_accounts.py` — idempotent, passwords from the environment, nothing
secret in the repo (INV-9). Creates admin + parent + provider (with an approved org
"Test Provider Co"). Run against **local and production with different passwords**.

Accounts: `admin@kidspots.store`, `parent@kidspots.store`, `provider@kidspots.store`.

**Credentials were handed over in the session chat and are not recorded here.** If they're
lost, re-run the script with new values — it resets rather than duplicates.

> **`admin@kidspots.store` already existed on production** and the run **reset its password**.
> The account, its admin flag and its history are intact, but any previously-known password
> for it is now void.

Verified in both environments: admin → 200 on the admin API, parent and provider → 403,
provider owns exactly 1 org.

---

## 5. What's remaining, in priority order

### Blockers — credentials, not code

1. **Stripe test keys.** Everything downstream is gated behind them: the live Payment
   Element, the party deposit and T-7d balance against real Stripe, webhook confirmation,
   Connect Express onboarding, T+2 transfers, Transfer Reversal on refund. The whole F-PAY
   track is complete and tested — but **only ever against `FakeGateway`**. See the
   milestone-C and status-audit handoffs for the exact verification plan.
2. **SMTP credentials** (Postmark or SES). The gateway is wired; it needs a host and a from
   address. This is what keeps `party_quotes` and `party_planner` dark — both are built,
   deployed and invisible.

### Worth doing soon

3. **Every e2e run makes billable Claude calls.** `JUGGLE_ANTHROPIC_API_KEY` is in `.env`, so
   the dev API's planner uses the live model. It also makes `planner-add-to-cart.spec.ts`
   flaky — the AI summary text varies between runs and sometimes trips a Playwright
   strict-mode locator. The same leak was fixed in pytest this morning (conftest forces the
   rule-based gateway); the e2e side is environmental — run it against an API started without
   that key.
4. **Deploy hardening** (`DEPLOY.md §9`) — Cloud SQL, Secret Manager, scheduled GCS backups.
   Currently container Postgres with manual pre-deploy dumps, which is fine for pre-launch
   and not fine with real customer data.

### Carried engineering debt

5. Admin tables aren't mobile-native — needs an `#item` card template per table. **Read the
   warning in §6 before touching them.**
6. SSR prefetch serialization, to avoid the client re-fetching what the server already had.
7. The deferred per-payout commit for the payout-release crash window (the release
   idempotency key covers normal retries).
8. Post-launch: no password-reset flow exists. Locked-out password users can only get back in
   via SMS code, or by an admin's help.

### Product direction

**No active gate.** ADR-0006 closed. Everything else in PRD-EXT-1 is locked until you raise
it: G1 share links, G3-full, G4 honest scarcity, G5 weekly digest, G6 referrals, E1/E3
pupil-free days and long weekends, E4 trial passes, the B-series, SMS, SSO, KidSport.

So the next decision is commercial, not technical: **spend on Stripe + Postmark and turn on
what's already built, or open a new gate and keep building while it stays dark.**

---

## 6. Traps found today — read before touching these areas

**Don't run `make worker-loop` while running the test suite.** The `db` fixture opens every
test with `DELETE FROM party_plan / platform_setting / feature_flag` inside its transaction,
holding table locks, while the worker tick writes `party_plan` on the same dev DB every 5
minutes. That collision produced a non-reproducing setup ERROR. With the worker stopped the
suite is clean. (Saved as a memory too.)

**Don't convert the admin tables to Quasar `grid` mode.** It's the obvious fix for the wide
tables and it **silently breaks them**: grid ignores `body-cell-*` slots, and all four admin
tables use them, so Approve/Suspend, Hold/Release, End-session and every status chip vanish.
I tried it and caught it in a screenshot — approvals rows rendered a bare UUID where the
buttons had been. `console-mobile-pages.spec.ts` now fails if someone tries again.

**Bottom-pinned CTAs must offset by `--jg-tabbar-h`.** The mobile tab bar is fixed; anything
using `position: sticky; bottom: N` will be hidden behind it. The variable is `0` on desktop
and `58px + env(safe-area-inset-bottom)` on mobile. Two checkout CTAs already use it.

**Deploy with `--iap`.** VM SSH is IP-restricted (`kidspots-ssh-allow`) and home IPs move —
mine had, which is why the first deploy failed with a port-22 timeout. The firewall already
allows Google's IAP range, so tunnelling beats reopening the firewall each time.

**Dialog widths:** use `min-width: min(Npx, 92vw)`, never a bare `min-width` over ~340px, or
the dialog forces horizontal page scroll on a phone.

---

## 7. Inherited beliefs that turned out to be wrong

Today corrected several things that had been repeated across handoffs and docs. Don't
re-inherit them:

| Belief | Truth |
| --- | --- |
| "The payout tests fail from shared-DB pollution but pass in isolation" | They **don't** pass in isolation. They asserted on the **global** payout table, so they were asserting the whole DB is empty. Fixed by scoping to the org under test. |
| "SSR is built but not in the prod deploy" | SSR has been **live in prod** since PR #20. |
| "Real email integration is missing" | The **`SmtpEmailGateway` exists**; only credentials are missing. |
| "A staff member without a verified WWCC can't be rostered (INV-4)" | **No such gate exists.** The roster is the list of *children*; there is no staff-assignment feature. INV-4 describes something unbuilt. Do not tell providers or families otherwise. |
| "Verification badges need WWCC + insurance + ABN together" | Four **independent** signals. |
| "Provider team members all have equal access" | `owner` vs `staff` — **cancelling a session is owner-only**. |
| "The planner's AI path is dormant" | `JUGGLE_ANTHROPIC_API_KEY` is set; it's **live** and billable. |

---

## 8. Services at close

All local Juggle services **stopped**: the API (`:8001`), the web dev server (`:9000`), the
maintenance worker, and the `jungler-db-1` Postgres container.

The database **volume is intact** — the container was stopped, not removed, so the dev data
and the seeded accounts survive. `make db` brings it back.

> Other containers on this machine (`tutoroo-*`) belong to a **different project** and were
> deliberately left running.

**Production was not touched** and is still serving.
