# Handoff — 2026-07-19 — Planner polish, AI composer, auth hardening

Session on branch **`feat/party-planner`** (continues the stack; base `main`, nothing merged).
Read `CLAUDE.md`, then the prior handoff `2026-07-15-auth-refresh-otp-ui-split-planner.md`, then this file.

---

## 1. TL;DR

Three threads landed, in this order, and are **committed locally** (not pushed) on top of `53d1098`:

1. **Planner polish** — the itinerary now varies activities across days, and there's a one-tap
   "add whole plan to cart". The "Perth Bowling ×5" I first saw was *sparse seed data*, not a bug.
2. **AI (Claude) composer verified** — the `AnthropicPlannerGateway` is correct for the installed
   `anthropic` 0.116 SDK; added mocked-SDK tests (success + fallback). Still dormant (no API key set).
3. **Auth hardening (handoff §6, all 7 items)** — OTP/refresh row-locks, SMS-bomb caps, phone-squatting,
   deleted/suspended enforcement, placeholder-email fix, token pruning. **Adversarially reviewed**
   (subagent) → 2 load-bearing findings fixed.

**State:** `make check` = ruff + mypy strict + import-linter clean. Backend **294 passed**; the only
failures are the **pre-existing §7 payout shared-DB pollution** (unchanged by this session — they touch
no payment code and pass in isolation). Web `vue-tsc` clean; new Playwright e2e green. Two migrations
applied (`96db45824a80` auth_throttle). Nothing merged; nothing pushed.

New commits (oldest→newest): `78ff8c8` feat(planner) · `9474616` feat(web) add-to-cart · `ae67ca4`
chore(web) dev proxy · `e1f6337` feat(auth) hardening.

---

## 2. What shipped

### A. Planner — diversify + add-to-cart (`78ff8c8`, `9474616`)
- **Diversification (backend):** added `program_id` to `CandidateSession`; `RuleBasedPlannerGateway`
  now does a **two-pass fill** — pass 1 fills each day with a *different* program (variety), pass 2
  allows repeats only to fill remaining days. Also fixed a UTC-vs-Perth day-grouping mismatch in the
  gateway (it grouped by UTC date while the service used Perth — INV-7). Variety hint added to the
  Claude system prompt. New test `test_rule_based_plan_varies_activities_across_days`.
- **The "all Perth Bowling" output was not a bug** — that suburb+window only has one matching program.
  Verified live: a Fremantle Sep–Oct brief returns a mixed Soccer/Bushrangers plan.
- **Add whole plan to cart (frontend):** `PlannerPage.vue` button matches each planned session to the
  parent's kids by age-at-start, holds a seat per matching child, adds each to the cart store. Reuses
  the session→hold→cart rails — **no new money code**. Skips age-mismatches, tolerates sold-out,
  guards double-add. Committed e2e `apps/web/e2e/planner-add-to-cart.spec.ts` drives it end-to-end.

### B. AI composer verification (`78ff8c8`)
- Confirmed against installed SDK: `client.messages.parse(model="claude-opus-4-8", output_format=PlanDraft)`
  → `message.parsed_output`; Opus 4.8 supports structured outputs. Two tests (mocked `anthropic`)
  cover the parsed-output success path (with an INV-3 assertion that only ages reach the model) and the
  fallback-to-rules-on-error path. **Dormant** until `JUGGLE_ANTHROPIC_API_KEY` is set + API restart.

### C. Auth hardening (`e1f6337`) — handoff §6, all 7 items
| # | Fix | Where |
|---|---|---|
| 1 | OTP brute-force → row lock on the challenge | `identity.service.verify_otp` |
| 2 | SMS-bomb/cost caps (per-number/day, per-IP/hour, global/hour) | new `AuthThrottle` + `_hit_rate_limit` / `_enforce_otp_send_limits`; route passes IP |
| 3 | Phone squatting → `phone` dropped from email signup (OTP-only binding) | `create_guardian`, `SignupRequest` |
| 4 | Refresh-rotation race → row lock | `rotate_refresh_token` |
| 5 | Deleted/suspended still valid → live-status gate every request | `deps._account_active` (keys on **admin actor** for impersonation tokens) |
| 6 | Placeholder-email 500 → reserved `.invalid` domain + IntegrityError-safe insert | `_find_or_create_by_phone`, `_is_reserved_email` |
| 7 | Unbounded growth → prune expired tokens/challenges/throttle rows | `prune_expired_auth` in the scheduler tick |

New settings knobs: `otp_max_per_number_per_day` (5), `otp_max_per_ip_per_hour` (5),
`otp_global_max_per_hour` (500). Migration `96db45824a80` adds `auth_throttle`.

---

## 3. Adversarial review (auth)
A subagent pressure-tested the auth diff. Two load-bearing findings, **both fixed**:
1. **Impersonation lockout** — `_account_active` checked the token's `sub` (the *target*), so an admin
   couldn't view-as a suspended/deleted account (a core support flow). Now keys on the impersonator for
   impersonation tokens. Test `test_impersonation_survives_target_deactivation`.
2. **Throttle get-or-create race → 500** — `SELECT … FOR UPDATE` can't gap-lock a non-existent row, so
   two first-requests for a new scope raced the unique index. Now savepoint-guarded (empirically
   verified SQLAlchemy expunges the pending row on nested rollback, leaving the tx usable).

Everything else the reviewer probed (verify_otp lock soundness, global-cap cost bound, prune keeping
reuse detection, no broken `create_guardian` callers, enum-status compare) checked out.

---

## 4. Invariants
- **INV-3:** planner still sends **ages only** to the model (tested); add-to-cart carries no child PII
  into holds beyond the existing child_ids.
- **INV-1:** add-to-cart and the hold-cleanup below go through `inventory.service` (seats_taken correct).
- **INV-7:** planner day-grouping now Perth in both service *and* gateway.
- **INV-10:** impersonation status gate deliberately keys on the admin, preserving §10.3 support access.

---

## 5. Known gaps / next steps
- **Not pushed, not merged.** All four commits are local on `feat/party-planner`.
- **Pre-existing §7 payout tests** (`test_payouts.py::test_admin_runs_due_payouts`,
  `::test_refund_before_release_claws_back_scheduled_payout`, and a cascade ERROR on
  `::test_future_payout_not_released`) fail against the **shared dev DB** (committed seed payouts).
  Same class as the firm-reservation global-count test. **Robust fix (deferred):** make these tests
  hermetic (clear the tables in the rolled-back per-test tx), *not* by deleting committed financial data.
- **Shared-DB e2e gotcha:** Playwright specs that create seat holds against the dev DB leave dangling
  browsing holds that trip `test_reserved_seat_survives_the_ttl_sweep` (a global `reclaim==0` assertion).
  Clean up with `inventory.service.force_release` (import `juggle.api` first). See the saved memory
  `e2e-shared-db-hold-pollution`.
- **AI planner** needs a real key to exercise the live Claude path (the whole contract is verified via
  mocks). **Auth item #5b:** `UserStatus.suspended` is now *enforced* but still never *assigned* anywhere
  — an admin "suspend user" action is a separate (unbuilt) feature. **Migration dedup (§6 #8):** N/A on
  this DB now that phone is only ever OTP-verified (unique by construction).
- Impersonation frontend fail-open items from the prior handoff §6 are **still open** (separate from this
  backlog).

---

## 6. How to run
Unchanged from the prior handoff, except **ports** (other apps occupy the defaults on this machine):
`make db` (Postgres :5433) · API on **:8001** (`uv run uvicorn juggle.main:app --reload --port 8001`) ·
web on **:9000** (`VITE_API_TARGET=http://localhost:8001 npm run dev` — `vite.config.ts` now reads
`VITE_API_TARGET`, default :8000) · worker loop running. Sanity: `curl localhost:8001/health`.

## 7. Where to look
- Planner: `apps/api/src/juggle/modules/planner/core/{gateway,schemas}.py`, `apps/web/src/pages/PlannerPage.vue`,
  `apps/web/e2e/planner-add-to-cart.spec.ts`, tests `apps/api/tests/test_planner.py`.
- Auth: `apps/api/src/juggle/modules/identity/core/{service,models,schemas}.py`,
  `apps/api/src/juggle/modules/identity/ui/routes.py`, `apps/api/src/juggle/deps.py`,
  `apps/api/src/juggle/modules/scheduler/core/service.py`, tests `apps/api/tests/{test_auth,test_impersonation}.py`,
  migration `apps/api/alembic/versions/96db45824a80_*.py`.
