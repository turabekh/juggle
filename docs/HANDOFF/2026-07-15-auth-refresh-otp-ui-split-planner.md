# Handoff — 2026-07-15 — Auth (refresh + SMS OTP + Twilio), UI split, AI planner

Session on branch **`feat/party-planner`** (continues the stack; base `main`, nothing merged).
Read `CLAUDE.md`, then the prior handoff `2026-07-14-party-page-ux-and-deploy.md`, then this file.

---

## 1. TL;DR

Five workstreams landed and are **pushed** to `origin/feat/party-planner` (HEAD `3028cb9`):

1. **Auth refresh fix** — the "token expires but never refreshes" bug had no fix because there was
   **no refresh mechanism at all**. Added **DB-backed, revocable, rotating refresh tokens** (15-min
   access + 30-day refresh) with reuse detection, plus a transparent frontend 401-refresh interceptor.
2. **SMS OTP sign-in** — one-time-code login behind an `SmsGateway` Protocol, now with a **real
   `TwilioGateway`** wired in, **fail-closed** when SMS isn't configured, and the login "Phone" tab
   gated on availability.
3. **UI split** — the confusing single app is now a **parent marketplace** and a separate **provider
   console** (sidebar chrome), behind **one login page** with a `[Parent | Provider]` toggle + header
   switchers.
4. **AI holiday planner** — a parent enters ages/dates/suburb/budget/interests → a day-by-day
   itinerary of **real, bookable** sessions. Rule-based by default; **Claude (`claude-opus-4-8`)**
   composes when a key is set. Behind the `planner` flag, OFF by default.
5. **`.env` location fix** — the app now reads the **repo-root `.env`** (matching `.env.example`)
   regardless of CWD.

**State:** backend `make check` = **285 passed** (ruff + mypy strict + import-linter clean); the only
2 failures are the **pre-existing payout shared-DB pollution** tests (unrelated — see §7). Web
`vue-tsc` + build + Vitest 23 green. Migration `aea752cb2932` applied. Nothing merged; nothing in
prod changed. **An adversarial code review was run** (2 subagents + own pass) — see §5/§6 for what's
fixed and what's outstanding.

---

## 2. What shipped (by workstream)

### A. Auth — refresh tokens (commit `23be2a9`)
- **Root cause:** a single 30-min access token, no refresh token, and no 401 handling on the client —
  so every session silently died at 30 minutes.
- **Now:** access token **15 min**; a **30-day refresh token** (opaque, `secrets.token_urlsafe(48)`,
  stored **SHA-256 hashed** in the new `refresh_token` table), **rotated on every use**.
- Endpoints: `POST /identity/refresh` (rotate), `POST /identity/logout` (revoke). Account
  deletion force-revokes all sessions.
- **Reuse detection:** replaying a rotated/revoked token revokes the whole token family. Subtlety:
  the revocation must be **committed even though the request 401s** — `get_session` rolls back on any
  raised exception, so the reuse path returns a `JSONResponse(401)` (does **not** raise) so the
  revocation commits. (A test-only false-positive was caught here — the shared-tx test couldn't
  distinguish commit vs rollback; verified against the live API instead.)
- **Frontend:** single-flight axios **401 interceptor** (`apps/web/src/lib/api.ts`) that transparently
  refreshes and replays the original request. Guarded so an **impersonation** token is never silently
  refreshed back into the admin session (`decodeJwt(token)?.imp` check).

### B. Auth — SMS OTP + Twilio (commits `23be2a9`, `1755feb`)
- `POST /identity/otp/request` (rate-limited per-number 60s, always **202** — no enumeration) →
  `POST /identity/otp/verify` (attempt-capped, single-use) → tokens.
- Codes are **keyed-hashed** (HMAC-SHA256 w/ JWT secret), TTL'd (10 min), never stored in
  `NotificationLog`. Phone normalized to E.164; verify does **find-or-create by phone** (phone-first
  accounts get a placeholder `@example.com` email; INV-3 — ages/adult-PII only, no child data).
- **`SmsGateway` Protocol** (in `notifications`): `FakeSmsGateway` (local dev, prints code to console)
  and **`TwilioGateway`** (real send, lazy-imports `twilio`). `get_sms_gateway()` returns Twilio when
  `JUGGLE_TWILIO_*` is set, else the fake **only in local dev**.
- **Fail-closed:** outside local dev with no provider, `/identity/otp/*` returns **503** and
  `GET /identity/auth-config` reports `sms_enabled:false`. The login **Phone tab is hidden** unless
  SMS is available.

### C. UI split — parent vs provider (commit `889a167`)
- **One login/signup page**: an **email / phone** tab set (phone only when SMS is on) and a
  `[Parent | Provider]` audience toggle that decides the post-login landing (`/discover` vs
  `/provider`); `?redirect=` still wins. Header **switchers** move dual-role users between the two.
- New **`ProviderLayout.vue`** — a sidebar console (like Admin) listing the user's organisations;
  provider routes moved under `/provider` (**route names + final URLs unchanged**). `MainLayout` is now
  purely consumer, with a "Switch to provider console" entry. Impersonation banner renders in the
  provider console too (INV-10).

### D. AI holiday planner (commit `9760567`)
- New **`planner` module** (above `search` in the import-linter layering). Stateless — no new tables.
- **Flow:** brief (ages + dates + suburb/budget/interests) → candidates pulled from the **live search
  projection** (INV-8/INV-12 — real, in-stock, bookable only) → composer selects from that set → the
  service **re-validates** output against candidates (drops hallucinations), prunes time-overlaps, and
  re-enforces budget → groups by Perth day (INV-7).
- **`PlannerGateway` Protocol**: `RuleBasedPlannerGateway` (deterministic day-packing; the default +
  the automatic fallback on any LLM error) and `AnthropicPlannerGateway` (`claude-opus-4-8` via
  `messages.parse()` with a Pydantic schema). **INV-3: only child AGES reach the model — never
  names/DOB/medical.**
- Gated on the **`planner` feature flag, OFF by default** (404 when off). Frontend `PlannerPage.vue`
  + "Holiday planner" nav (signed-in only).

### E. `.env` location fix (commit `3028cb9`)
- The API runs from `apps/api`, so `env_file=".env"` never found the repo-root `.env` that
  `.env.example` tells you to create. `settings.py` now resolves `.env` by **absolute path from the
  package root** (`Path(__file__).resolve().parents[4] / ".env"`); missing files are ignored, so
  Docker/prod (which inject real env vars) are unaffected. Test client **forces the fake SMS gateway**
  so real Twilio creds in `.env` can't trigger a live send during the suite.

---

## 3. Architecture / new & changed surfaces

### Backend
- **New:** `refresh_token` + `otp_challenge` tables (`identity.core.models`), migration
  `aea752cb2932`. `phone` on `user_account` is now **unique** (Postgres NULLs distinct).
- **New module `planner`** — `core/{schemas,gateway,service}.py` + `ui/routes.py`. No models.
- `security.py` — `generate/hash_refresh_token`, `generate/hash_otp_code`, `verify_secret`.
- `notifications.core.gateway` — `SmsGateway`/`FakeSmsGateway`/`TwilioGateway` + `sms_configured()`
  / `sms_available()` / `get_sms_gateway()`; `notifications.core.service.send_login_code`.
- `settings.py` — `access_token_ttl_minutes=15`, `refresh_token_ttl_days=30`, `otp_*`,
  `twilio_*`, `anthropic_api_key`/`anthropic_model`; root-`.env` loading.
- Deps: `anthropic>=0.40`, `twilio>=9.10.9` (+ mypy override for `twilio.*`). `planner` added to the
  import-linter layering (above `search`).

### Frontend (`apps/web`)
- `lib/api.ts` — token state + `configureAuth`, single-flight refresh interceptor, `auth.config()`,
  `auth.requestOtp/verifyOtp/logout`, `planner.plan()`.
- `stores/auth.ts` — rewritten: `applyTokens`, refresh callbacks, OTP login, server-side logout,
  impersonation-safe enter/exit/restore.
- `lib/authAudience.ts` — audience type + landing helper. `lib/jwt.ts` unchanged.
- Pages: `LoginPage.vue` (tabs + audience toggle + Phone-tab gating), `SignupPage.vue` (audience),
  `PlannerPage.vue` (new). Layouts: `ProviderLayout.vue` (new), `MainLayout.vue`. `router/index.ts`
  (`/provider` parent route + `/planner`). `pages/provider/ProviderDashboard.vue` (emits `orgs-changed`).

---

## 4. Invariants (how respected)
- **INV-2 (money):** untouched by any of this work.
- **INV-3 (child PII):** OTP/refresh carry adult PII only; the planner sends **ages only** to the LLM,
  and its request/candidate schemas have **no** name/DOB/medical field (tested).
- **INV-7:** planner groups the itinerary by `Australia/Perth` day.
- **INV-8/INV-12:** planner candidates come from the live search projection — real, in-stock,
  bookable; the composer can only select from them (hallucinations dropped).
- **INV-9:** no secrets committed. `.env` is gitignored; `.env.example` documents the contract with
  blank placeholders. **Note:** the Twilio Auth Token was surfaced in this session's context — consider
  rotating it.
- **INV-10 (impersonation):** banner rendered in the provider console; the refresh interceptor refuses
  to refresh an impersonation session. **Two hardening items remain — see §6.**

---

## 5. Review gates
- **Adversarial code review** run (two independent subagents: backend-auth security + frontend/session;
  plus an own prod-readiness pass). All load-bearing findings were verified against the code.
- **What the review drove to done this session:** SMS OTP made prod-viable (real Twilio + fail-closed
  + tab gating + the console `print` is now local-dev-only); the reuse-revocation commit bug; the
  impersonation-refresh guard; and the `.env` loading bug.
- **Verification:** backend `make check` (285 pass); browser-driven end-to-end for OTP login,
  transparent refresh (forge-expire the access token → interceptor refreshes → stays logged in), the
  parent/provider split + switchers, and the planner itinerary. API-level end-to-end for the planner
  and refresh rotation/reuse/logout.

---

## 6. Known gaps / next steps (prioritised)

**Auth hardening (from the review — NOT yet done):**
- **OTP brute-force is concurrency-unsafe** — `verify_otp` reads/increments `attempts` with no
  `SELECT … FOR UPDATE`; parallel guesses can exceed the cap. Add a row lock. (`identity.core.service`)
- **SMS bombing / cost** — only a per-number 60s cooldown; **no per-IP / global / per-day cap.** The
  repo already has an IP throttle pattern (`party_planner`'s `PlanThrottle`) to reuse.
- **Phone squatting** — signup stores the phone **raw and unverified** while OTP resolves on the
  **normalised** form; an attacker could pre-register a victim's normalised number. Normalise + verify
  phone at signup, or don't let an unverified signup-phone satisfy OTP resolution.
- **Refresh rotation has no row lock** — two concurrent rotations of one token both succeed and fork
  the family without firing the reuse alarm. Add `with_for_update()`.
- **Access tokens ignore account status for their 15-min life** — `get_current_principal` never loads
  the user, so a deleted/suspended account keeps access until the token expires. Also
  `UserStatus.suspended` is **never assigned** anywhere (dead guard).
- **Placeholder-email collision** — `sms-{phone}@example.com` is registerable; a pre-registered
  collision 500s a victim's first OTP. Catch the `IntegrityError` / use a non-registerable form.
- **Unbounded growth** — nothing prunes `refresh_token` / `otp_challenge`. Add a scheduler sweep.
- **Migration `aea752cb2932`** adds the unique `phone` index with no dedup/backfill (fine on this DB,
  risky on prod data with existing duplicate/raw phones).

**Impersonation hardening (before enabling impersonation in prod, INV-10):**
- Frontend **fail-open guard**: during impersonation the admin's refresh token stays live in memory;
  the only thing stopping a 401 from minting a fresh admin session is a client-side `decodeJwt`
  succeeding. Null the refresh token on `enterImpersonation`, restore on exit.
- **Reload mid-impersonation** logs the admin fully out (expired imp token → `restore()` catch wipes
  `ADMIN_BACKUP_KEY`). Fall back to the admin backup instead.

**Other:**
- `?redirect=` is pushed via `router.push` unvalidated (not a working open-redirect via vue-router,
  but add a `^/(?!/)` in-app-path guard). (`lib/authAudience.ts`)
- Provider sidebar org name/status goes stale until reload (only Dashboard emits `orgs-changed`).
- **No password-reset flow** anywhere (and it'd need the still-absent real **email** gateway).
- **Payout test pollution** (see §7).
- Planner: itinerary items link into the existing session→hold→cart→checkout rails; a one-tap "add
  whole plan to cart" is the natural next step (no new money code needed).
- SMS launch prerequisites otherwise met, but the OTP hardening above should land before real users.

---

## 7. The 2 failing payout tests (pre-existing, not this session)
`tests/test_payouts.py::test_admin_runs_due_payouts` and `::test_refund_before_release_claws_back_
scheduled_payout` assert **global** payout emptiness, but the shared dev DB has committed seed payouts
("Sunshine Kids Co", dated 2026-07-12/14 — before this session). This is the shared-DB count fragility
the prior handoff documents. Nothing in this session touches payouts. **Do not "fix" by deleting
committed financial data** (bookings reference `payout_id`); the robust fix is to make those tests
hermetic (clear payout tables in the rolled-back per-test tx, like `party_plan`/`config`/`flags` in
`conftest`) — deferred.

---

## 8. Git / PRs
Branch `feat/party-planner` (base `main`; nothing merged). All work **pushed**; `HEAD = origin = 3028cb9`.

| commit | what |
| --- | --- |
| `23be2a9` | `feat(auth)` DB-backed refresh tokens + SMS OTP (backend + store/api) |
| `889a167` | `feat(web)` one login (email/phone/parent/provider) + split provider console |
| `9760567` | `feat(planner)` AI holiday-activity planner (rule-based + Claude) |
| `1755feb` | `feat(auth)` Twilio SMS + fail-closed OTP + Phone-tab gating |
| `3028cb9` | `fix(config)` load repo-root `.env` regardless of CWD + hermetic-SMS test client |

Note: shared cross-cutting files (`settings.py`, `api.ts`, `types.ts`) carry more than one workstream;
commit scoping is by dominant theme.

---

## 9. How to run / configure

**Dev stack:** `make db` · `make dev` (API :8000) · `make web-dev` (web :9000).

**Local config lives in the repo-root `.env`** (copy of `.env.example`; **gitignored**). Relevant keys:
- **Twilio SMS** — `JUGGLE_TWILIO_ACCOUNT_SID` / `_AUTH_TOKEN` / `_FROM_NUMBER` (E.164). All three set
  → real SMS. Blank → console fake in local dev only. **Changing `.env` requires an API restart**
  (settings are cached per-process; `--reload` watches `.py`, not `.env`).
- **AI planner** — `JUGGLE_ANTHROPIC_API_KEY` (+ optional `JUGGLE_ANTHROPIC_MODEL`, default
  `claude-opus-4-8`). Blank → deterministic rule-based planner.
- **Feature flags** — the `planner` flag is OFF by default; enable via the admin flags page or
  `PUT /api/v1/flags/planner {"enabled":true,"rollout_percentage":100}` (admin token). `party_planner`
  similarly enabled locally via `make seed`.

**Try it:**
- **Refresh/OTP:** `/login` → Phone tab (visible when SMS available) → code → signed in. Sessions now
  survive past 15 min via transparent refresh.
- **Split:** login toggle Parent vs Provider; header switchers move between them; provider console at
  `/provider` with a sidebar org list.
- **Planner:** enable the `planner` flag → `/planner` → ages/dates/suburb/budget/interests → itinerary.

> **Sanity checks:** `curl localhost:8000/api/v1/identity/auth-config` (SMS availability);
> planner API returns `generated_by: "rules"` (no key) or `"ai"` (key set).

---

## 10. Where to look
- **Auth backend:** `apps/api/src/juggle/security.py`,
  `apps/api/src/juggle/modules/identity/{core,ui}/`,
  `apps/api/src/juggle/modules/notifications/core/{gateway,service}.py`, migration
  `apps/api/alembic/versions/aea752cb2932_refresh_tokens_otp_challenge_phone_.py`,
  tests `apps/api/tests/test_auth.py`.
- **Auth frontend:** `apps/web/src/lib/{api,authAudience}.ts`, `apps/web/src/stores/auth.ts`,
  `apps/web/src/pages/{LoginPage,SignupPage}.vue`.
- **UI split:** `apps/web/src/layouts/{ProviderLayout,MainLayout}.vue`,
  `apps/web/src/router/index.ts`, `apps/web/src/pages/provider/ProviderDashboard.vue`.
- **Planner:** `apps/api/src/juggle/modules/planner/`, tests `apps/api/tests/test_planner.py`,
  `apps/web/src/pages/PlannerPage.vue`.
- **Config:** `apps/api/src/juggle/settings.py`, `.env.example`, `apps/api/tests/conftest.py`.
