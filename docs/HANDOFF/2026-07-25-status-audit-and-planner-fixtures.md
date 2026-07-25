# Handoff — 2026-07-25 — Status audit, prod reality-check, green suite, user suspension

Session on branch **`fix/planner-test-date-fixtures`** (base `main` @ `b2645e2`, nothing pushed —
the branch name undersells it; it also carries the payout-test fix and the suspension feature).
Read `CLAUDE.md`, then this file. The prior handoff (`2026-07-19-planner-polish-ai-auth-hardening.md`)
is **stale in one important way**: it says its work was unmerged on `feat/party-planner`. It merged
that afternoon (PR #9), and **ten more PRs landed on 2026-07-19…21 with no handoff written**. §2
below is the missing record.

---

## 1. TL;DR

- **Juggle is live in production at https://kidspots.store**, serving **request-time SSR** (verified:
  fully rendered markup + `window.__PINIA__` in the response), with the API on `/api/v1/*`.
- **Two live hazards found by inspection** (§4): prod runs the **`FakeGateway`** (no Stripe keys), so a
  real checkout there confirms a booking and accrues a payout against money never collected; and the
  **backend test suite was calling the real Claude API** on every run because `JUGGLE_ANTHROPIC_API_KEY`
  is now set in `.env`. The second is fixed here; the first is a decision for the next session.
- **Fixed:** the 5 planner test failures — hardcoded `2026-07-20 → 2026-07-25` fixtures that expired on
  the calendar, not a regression — plus the live-API leak that hid behind them, and the two payout
  failures that had been mis-diagnosed for weeks.
- **State:** `make check` = ruff + mypy strict + import-linter clean, **312 passed, 0 failed** — the
  two long-standing payout failures are fixed too (§3D), so the backend suite is green for the first
  time in a while. Web: `vue-tsc` clean, build green, 27 Vitest units pass.

- **Shipped:** admin **user suspension / reinstatement** — `UserStatus.suspended` was enforced in
  three places but assignable from nowhere, so that enforcement was unreachable code. Now it isn't.

New commits (oldest→newest): `aaff682` fix(tests) planner date fixtures + planner-gateway override ·
`87220c9` fix(tests) scope payout assertions + CLAUDE.md status refresh ·
`2d08ff7` docs this handoff · `5561738` feat(admin) suspend/reinstate a user account.

---

## 2. The missing record — PRs #10–#20 (2026-07-19 → 07-21)

Ten PRs merged to `main` after the last handoff was written. In order:

| PR | Commit | What |
| --- | --- | --- |
| #10 | `94839bc` | **fix(web): close impersonation fail-open + reload logout (INV-10).** The admin's *refresh* token is now pulled out of play for the duration of an impersonation (backed up to `juggle.adminRefresh`, nulled in memory/storage, restored on exit). The api layer already refused to refresh an impersonation session, but that guard is a client-side JWT decode — nulling the refresh token is the fail-closed backstop. Closes the prior handoff's last open item. |
| #11 | `208bd08` | **chore(deploy): target kidspots.store apex + run sheet** — `docs/DEPLOY-kidspots.md` (VM, firewall, Namecheap apex A record, admin promotion), `.env.production.example`. |
| #12 | `fec8cf4` | **fix(settings): don't crash resolving repo root in a shallow container tree.** |
| #13 | `c9321f6` | **docs: admin / provider / parent user guides** (`docs/GUIDE-{admin,provider,user}.md`, ~740 lines). |
| #14 | `83c1585` | **chore(deploy): `scripts/deploy.sh`** for the GCE VM. |
| #15 | `15b9927` | **fix(deploy): archive-push model + container healthcheck gate.** The repo is private and the VM has no GitHub credentials, so deploys **ship a `git archive` tarball** of a local branch and extract it over the VM checkout — there is no `git pull` on the VM. The VM's `.env` is never in the archive. |
| #16 | `dc3f53a` | **chore(seed): `apps/api/scripts/seed_prod_catalog.py`** — catalog-only, production-safe supply data (1 org, 3 venues, 5 programs, 3 party packages). Creates no admin, no families/bookings, changes no flags; idempotent (INV-9). |
| #17 | `e0685b3` | **feat(notifications): real SMTP email gateway behind the Protocol.** `SmtpEmailGateway` (Postmark/SES/any), selected when `JUGGLE_EMAIL_SMTP_HOST` + `JUGGLE_EMAIL_FROM_ADDRESS` are set, else the fake. stdlib `smtplib`, imported lazily. Tests in `test_email_gateway.py`. |
| #18 | `39a5fe2` | **chore(ops): `scripts/kidspots-backup.sh` + `kidspots-restore-test.sh`** + `DEPLOY.md §9`. |
| #19 | `be63885` | **feat(web): unblock request-time SSR — no Quasar-CLI migration.** `@quasar/vite-plugin` has a built-in `runMode: 'ssr-server'`; older handoffs claiming SSR needed a CLI migration were **wrong**. Per-page meta + Event JSON-LD render server-side; SEO pages use `onServerPrefetch`. |
| #20 | `0e52d13` | **feat(deploy): serve SSR in production.** Caddy now reverse-proxies `/api/*` → api:8000 and everything else → the **`ssr` node service (`server.mjs`, :5173)**, which renders HTML and serves `dist/client`, with an SPA-shell fallback on SSR error. |

Prod topology is now: `db → migrate (one-shot alembic) → api + worker → ssr → web (Caddy/TLS)` in
`docker-compose.prod.yml`, on one GCE VM in `australia-southeast1`.

---

## 3. What this session did

### A. Restarted the stack + audited where the project actually is
Ports (defaults are taken on this machine): db `:5433`, API `:8001`, web `:9000`, worker looping.
Migrations at head (`96db45824a80`). Verified against the **active gate** (ADR-0006):

| Milestone | State |
| --- | --- |
| A — any-day one-off sessions | **Done** — `weekend`/`weekday`/`after_school` facets, `/search/feeds/this-weekend`, `/feeds/after-school`, `admin.reject_listing(recurring_enrolment)` |
| B — parties instant-book | **Done** — packages, capacity-1 slots, deposit, T-7d balance, adjust/cancel (ADRs 0007–0010) |
| C — parties request-to-quote | **NOT STARTED.** ADR-0009 decided quote expiry/counters, but `grep -ril quote` over `apps/api/src`, `apps/web/src`, `apps/api/tests` returns **zero hits** |
| D — G2 party planner | **Done** — vote-to-book, RSVP, flag on |

### B. Fixed the planner test fixtures (`tests/test_planner.py`)
5 failures, all one cause: `MON/TUE/WED_A/WED_B` were hardcoded to `2026-07-20…22` and `_brief()` to
`2026-07-20 → 25`. `search_sessions` filters `starts_at >= now` (`search/core/service.py:86`), so once
the calendar passed those dates every planner candidate query returned empty (`candidate_count == 0`).
A **date time-bomb, not a regression** — it would have failed identically on `main` with no code change.

Replaced with a relative `_window(days_ahead, start_hour=9, hours=2)` helper returning aware UTC
datetimes for Perth-morning windows, plus `PLAN_FROM`/`PLAN_TO` (today → +5d). Perth-morning windows
are deliberate: 09:00 Perth = 01:00 UTC keeps the Perth and UTC **calendar dates identical**, and the
search date filter bounds on UTC days (INV-7). Constants renamed `DAY_1`/`DAY_2`/`DAY_3_A`/`DAY_3_B`
(the old weekday names would now be lies), with titles/comments following.

### C. Fixed a live-API leak in the test suite (`tests/conftest.py`)
With the fixtures repaired, one test still failed — `generated_by == 'ai'`, not `'rules'`. Cause:
`JUGGLE_ANTHROPIC_API_KEY` is now set in `.env`, so `get_planner_gateway()` returned the
**`AnthropicPlannerGateway`** and **every planner test made a real, billable Claude call** (the run
took 7.1s; after the fix, 1.9s).

The `client` fixture already forced the fake SMS gateway "so a developer's real Twilio creds in `.env`
can never trigger a live send (or cost)". Applied the same treatment: it now overrides
`get_planner_gateway` → `RuleBasedPlannerGateway`. The Anthropic path keeps its own coverage against a
mocked SDK, so nothing is lost.

### D. Fixed the payout tests properly (`87220c9`)
Not "shared-DB pollution that passes in isolation" (see §6) — they asserted on the **global** admin
payout list, so they were really asserting the whole database is empty. Added `_org_payouts()` and
scoped every assertion to the org the test creates. Two latent versions of the same bug fixed while
there: `test_hold_blocks_release` took `scheduled[0]` off the global list (it could have put a *seed*
payout on hold) and `test_future_payout_not_released` asserted a global `released == 0`. **No
production code touched** — this is test scoping only, and the payments deferral is respected.

### E. Admin user suspension / reinstatement (`5561738`)
The auth-hardening batch (§2 of the prior handoff, item #5) made `UserStatus.suspended` enforced in
three places — `authenticate` refuses a login, `rotate_refresh_token` refuses a refresh, `deps`
re-checks live status on every request — but **nothing could assign it**, so the whole path was
unreachable. Closed:

- **`identity.set_account_status()`** flips `active ↔ suspended` and revokes every live refresh
  token. The revoke is what makes suspension *immediate* rather than eventual — the access token
  dies on its next request and there is nothing left to mint a replacement. (Belt and braces: even
  if a concurrent login won the race and minted a token just before the flip committed, refresh and
  every request re-check live status, so the surviving token is inert.)
- **`deleted` is terminal in both directions** (`AccountDeleted`, 409): §10.2 anonymisation must go
  through `delete_account`, and a data-deleted account has no PII left to restore.
- **Guards**, mirroring the existing `CannotDeleteAdmin` precedent: no self-suspension, and admin
  accounts cannot be suspended — they are provisioned/revoked at the DB layer (no admin-creation
  endpoint by design), so allowing it would create an in-app lockout with no in-app recovery.
- **Impersonation cannot reach it**: `create_impersonation_token` forces `adm=False`
  (`security.py:108`), so `get_current_admin` rejects impersonation tokens outright and the audited
  actor is always a real admin (INV-10).
- Both actions audited with the true actor + the operator's reason. UI: status badge in the results
  list, suspend (with reason prompt) / reinstate on the selected user. `GUIDE-admin.md §3` updated.
- 10 new tests (`tests/test_user_suspension.py`) covering the three-way lockout, force-logout across
  devices, reinstatement, every guard, and the audit detail.

**Not adversarially reviewed by a subagent** (out of scope this session per instruction) — the
self-review above is what it got. It touches auth, so a fresh skeptical pass before merge is worth it.

### F. Two carried-over party-planner nits closed
- **Post-tie final-pick notice** (open since the 2026-07-12 handoff). When a vote ended in an
  unbroken tie the reveal told invitees "a tie — the host will decide", and then **nothing**: the
  change-of-plans email only fires when a *real* announced winner is overridden, so guests never
  learned the outcome. `confirm_booking` now branches — tie → new `notify_planner_final_pick`
  ("the host has picked"), overridden winner → the existing change notice, and booking the winner
  the reveal already announced stays silent (no duplicate news). Two tests, including the silence case.
- **Party-page counter limits** were hardcoded client-side (`TITLE_MAX = 60`, `MESSAGE_MAX = 280` in
  `PartyPageEditor.vue`) while the real caps are runtime config (INV-11) — an admin change would have
  left the editor lying. `PlanView` now carries a `limits` block read live from `config`, and the
  editor's counters follow it. The related half of the nit is fixed too: `PagePatchIn`'s outer
  `max_length` was 200/2000, looser than the config bounds, so a 150-char title 422'd while a
  100-char one silently truncated — the outer bounds are now the config specs' own maxima (120/1000),
  so anything an admin could configure truncates cleanly and the payload guard stays honest.

---

## 4. Findings that need a decision (not fixed here)

1. **Prod is running the FakeGateway.** `https://kidspots.store/api/v1/payments/config` returns
   `{"live":false,"publishable_key":null}` — no `JUGGLE_STRIPE_*` on the VM. The checkout flow there
   will happily confirm a booking, accrue a provider payout, and send a confirmation email for money
   that was never taken (the sync `confirm()` endpoint is only 409-gated *under live Stripe*). Either
   put test/live keys on the VM or gate checkout in prod until they exist. **This is the top item.**
2. **`CLAUDE.md`'s Status paragraph is stale** — it still says SSR is "not yet wired into the prod
   deploy" and lists "real email integration" as a remaining gap. Both landed (PRs #17, #19, #20).
   Worth a docs pass on merge.
3. **The payments track has never touched real Stripe.** F-PAY-1…6 are complete and tested, but every
   test runs on `FakeGateway`: webhook signature verification, the `stripe_event` ledger, Connect
   Express onboarding, T+2 `Transfer`, and Transfer Reversal on refund are verified by contract only.
   Building Milestone C on those rails widens untested surface — do the Stripe test-mode pass first.

---

## 5. Invariants

- **INV-7** — the new fixture helper is explicitly Perth-aware and documents why morning windows keep
  the UTC and Perth calendar dates aligned against the UTC-day search bound.
- **INV-3** — untouched; the planner still sends ages only, and `test_planner_request_carries_no_child_pii`
  plus the mocked-SDK payload assertion both still pass.
- **INV-2 / INV-5** — no money code touched this session. But see §4.1: prod's current gateway state
  means INV-2's "money moves only through `payments`" is technically satisfied while *no money moves at all*.
- **INV-10** — closed out by PR #10 (§2); the admin refresh token is now fail-closed under
  impersonation. Suspension respects it too: impersonation tokens can't reach the new routes
  (`adm=False`), and every suspend/reinstate is audited with the true actor.
- **INV-3** (again, suspension) — no child data involved; suspension touches only `user_account.status`
  and refresh tokens, and the audit detail carries a status + operator reason, never PII.

---

## 6. Known gaps / next steps

> Payments work was **explicitly deferred** by the operator this session, which is why the Stripe
> verification below was not started and the suspension feature was picked up instead.

**Recommended next step (when payments are back on the table): wire Stripe test keys and verify the
live payment path end to end.** Needs a
Stripe test-mode account (publishable + secret) and a webhook secret from
`stripe listen --forward-to localhost:8001/api/v1/booking/stripe/webhook`, plus test-mode Connect
Express. Then: provider onboarding → `account.updated` capability sync → Payment Element checkout →
`payment_intent.succeeded` → confirm → payout accrual → refund + clawback (both the scheduled-decrement
and Transfer-Reversal branches) → tax invoice; then party deposit + balance charge. Adversarial review
on the diff per `CLAUDE.md`.

**Non-payment work, in the order I'd take it:**
- **SMTP credentials** (Postmark or SES) — needs an account, not code. Gateway is done (#17) and it is
  the hard dependency keeping `party_planner` OFF in prod. Highest value per effort of anything left.
- **Milestone C** (request-to-quote) — the only unbuilt piece of the active gate, but note its
  definition of done ends in a deposit on Milestone B's rails, so the last leg is payments work.
  The brief → quote → accept state machine and its expiry job can be built without touching money.
- ~~Post-tie final-pick notice / party-page config-driven counter limits~~ — **both done** (§3F).
- ~~Pre-existing payout test failures~~ — **fixed** in §3D. Worth recording why they survived so long:
  every prior handoff repeated that they "pass in isolation" and blamed shared-DB pollution. They do
  not pass in isolation, and the pollution was not the bug — the tests asserted on the global payout
  table, so any committed payout anywhere broke them. The inherited diagnosis is what kept them open.
- Carried over: SSR prefetch serialization to avoid the client hydration re-fetch; deploy hardening
  (Cloud SQL + Secret Manager + scheduled GCS backups, `DEPLOY.md §9`).
- **Shared-DB e2e gotcha** (unchanged): Playwright specs that create seat holds leave dangling browsing
  holds that trip `test_reserved_seat_survives_the_ttl_sweep`. Clean up with `inventory.service.force_release`.
- **New gotcha — don't run `make worker-loop` while running the suite.** One full run here produced a
  non-reproducing `ERROR tests/test_party_planner.py::test_removing_voted_option_voids_its_tally`
  (passes alone, passes with its file, passes with its neighbours, and did not recur). The `db`
  fixture opens each test with `DELETE FROM party_plan / platform_setting / feature_flag` inside its
  transaction, holding table locks for the test's duration, while the worker tick writes `party_plan`
  (`resolve_due_plans` / `sweep_stale_resolved` / `purge_expired_plan_pii`) against the same dev DB
  every 5 minutes. **Confirmed:** with the worker stopped, the same suite is **312 passed, 0 failed,
  0 errors**. Stop the worker before `make check`.

---

## 7. Where to look

- This session's diff: `apps/api/tests/{test_planner,conftest,test_payouts,test_user_suspension,test_party_planner}.py`;
  `identity/core/service.py` (`set_account_status`), `admin/core/{service,schemas}.py`,
  `admin/ui/routes.py`, `party_planner/core/{service,schemas}.py` (final-pick notice + `PlanLimits`),
  `notifications/core/service.py` (`notify_planner_final_pick`),
  `apps/web/src/pages/admin/AdminUsersPage.vue`, `apps/web/src/components/PartyPageEditor.vue`,
  `apps/web/src/lib/{api,types}.ts`.
- Why the fixtures expired: `apps/api/src/juggle/modules/search/core/service.py:86` (`starts_at >= now`)
  and `:43` (`_day_start`, UTC day bounds).
- Gateway selection points: `planner/core/gateway.py:187` (`get_planner_gateway`),
  `payments/core/gateway.py:356` (`get_payment_gateway`), `notifications/core/gateway.py` (email + SMS).
- Prod: `scripts/deploy.sh`, `docker-compose.prod.yml`, `apps/web/Caddyfile`, `docs/DEPLOY-kidspots.md`.
- Active gate: `docs/PLANS/always-on-marketplace.md`, `docs/ADR/0006`, `0007`–`0011`.

## 8. How to run

`make db` (Postgres :5433) · API `uv run uvicorn juggle.main:app --reload --port 8001` ·
web `VITE_API_TARGET=http://localhost:8001 npm run dev` (:9000) · `make worker-loop`.
Sanity: `curl localhost:8001/health`. Prod: `scripts/deploy.sh --backup`.
