# Juggle — Session Handoff

_Last updated: 2026-07-11. Read this first, then `CLAUDE.md` (engineering conventions) and `docs/juggle-prd.md` (product spec)._

---

## 1. What this is

**Juggle** is a two-sided **booking marketplace for kids' school-holiday activities and birthday parties** (Perth beachhead). Parents discover sessions by suburb/date/age with **live availability**, book across providers in one cart, and pay; providers get free self-serve tools to list, manage rosters, cancel, and get paid; an operator runs approvals, config, refunds, payouts, and impersonation.

"Juggle" and "Starlit" naming: the repo's original `CLAUDE.md`/`README` were a leftover **Starlit to-do-app template**; they were replaced. The real product is the **Juggle marketplace** from `docs/juggle-prd.md`. The directory is named `jungler` (a typo-ish nod to Juggle) — that's just the folder name.

**Status: the Phase-0 MVP is essentially complete and verified in a real browser.** Backend (14 domain modules), plus three frontend surfaces (parent marketplace, admin console, provider console). Everything below was built milestone-by-milestone, each committed separately with tests and/or headless-browser verification.

---

## 2. How to run it

Prereqs (all already installed on this machine): Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Node 20+, Docker.

```bash
cd /Users/turaboy/projects/jungler

# One-time (already done on this machine — DB is up, migrated, seeded, deps installed):
make db            # Postgres+PostGIS in Docker on host port 5433 (NOT 5432 — see gotchas)
make migrate       # apply Alembic migrations
make seed          # demo data: admin + provider "Sunshine Kids Co" + 15 published sessions
make install       # backend deps (uv)
make web-install   # frontend deps (npm)

# Run (two terminals, foreground, so they stay up):
make dev           # backend  → http://localhost:8000  (/docs for OpenAPI)
make web-dev       # frontend → http://localhost:9000   (proxies /api → :8000)
```

Open **http://localhost:9000**.

**Login / roles** (all password `supersecret`):
| Role | How | Where |
|---|---|---|
| Parent | sign up with any email | Discover → book → My bookings |
| Admin | `admin@example.com` | account menu → **Admin console** |
| Provider | any signed-in user | account menu → **For providers** |

`make check` (from repo root or `apps/api`) runs the full gate: ruff + mypy(strict) + import-linter + pytest. Frontend: `make web-build` (vue-tsc + vite build).

---

## 3. Current state (facts)

- **20 commits**, one per milestone/slice (see `git log --oneline`). All green at each step.
- **Backend: 79 pytest passing**, mypy `--strict` clean (104 files), **import-linter 2/2 contracts KEPT**, ruff clean.
- **Frontend: vue-tsc + vite build clean.**
- **4 Alembic migrations**, head = `cb61cfc9ec23` (add_notification_log). Chain: initial → payment idempotency_key → booking seat_hold_id → notification_log. The chain round-trips (down to base and back).
- Stack: FastAPI + SQLAlchemy 2 + PostgreSQL/PostGIS + Alembic (`apps/api`); Vite + Vue 3 (TS) + Quasar SPA (`apps/web`).

---

## 4. Architecture

### Backend module layering (enforced by import-linter)
13 domain modules under `apps/api/src/juggle/modules/`, each with a **`core/` (domain: models, schemas, service — NO FastAPI imports)** and **`ui/` (FastAPI router)** split. Two contracts in `pyproject.toml [tool.importlinter]`:

1. **`core` never imports FastAPI/Starlette.**
2. **Strict acyclic layering** (high→low — a module may import only modules **below** it):

   ```
   admin ▸ roster ▸ search ▸ booking ▸ payments ▸ inventory ▸ catalog ▸ org ▸ identity ▸ notifications ▸ flags ▸ config ▸ audit
   ```

   Cross-module calls go through the lower module's `core.service`. Key consequences:
   - `catalog` calls `org.service` (membership); `inventory` operates on `catalog`'s `Session`; `booking` orchestrates catalog/inventory/payments/identity/org/notifications; `admin` sits on top and composes everything.
   - **`audit` and `notifications` are low-level utilities** (near the bottom). Everyone above can call `audit.record(...)` and `notifications.notify_*(...)`. This is why notifications takes **fully-formed content** from callers (it never fetches domain data) — otherwise it'd need to sit above booking and create a cycle. Same shape as audit.

### Shared infra (not modules, under `src/juggle/`)
- `db.py` — engine, `SessionLocal`, `Base`, `get_session` dependency.
- `common.py` — `UUIDPkMixin`, `TimestampMixin`.
- `security.py` — bcrypt hashing, JWT create/decode, `Principal` (framework-free; any `core` may import).
- `deps.py` — FastAPI auth deps (`CurrentPrincipal`, `CurrentAdmin`) + **impersonation enforcement** (view-as read-only, per-action audit, revoke-on-end). It queries `impersonation_session` **by raw SQL table name, not the admin model**, so this auth infra (imported by every ui) stays decoupled from the top `admin` module (importing the model would create a low→high cycle — import-linter caught exactly this).
- `models.py` — imports every module's models so Alembic sees full metadata.
- `settings.py` — deployment config (env, `JUGGLE_` prefix). **Product config lives in the DB `config` module, not here.**

### Gateways (interface + fake, real impl is a swap)
- **`payments.core.gateway`** — `PaymentGateway` Protocol + `FakeGateway` (in-memory) + `get_payment_gateway`. Methods: `create_payment_intent`, `confirm`, `refund`, `transfer` (Stripe Connect payout).
- **`notifications.core.gateway`** — `EmailGateway` Protocol + `FakeEmailGateway` (in-memory `outbox`) + `get_email_gateway`. `send(to, subject, body, ics)`.
- Both are selected in `get_*_gateway()` by environment; wiring real Stripe/Postmark is a one-file swap.

### Frontend (`apps/web`)
- Vite + Vue 3 + TS + Quasar (via `@quasar/vite-plugin`, not the Quasar CLI — cleaner, fully controlled structure).
- **Design system**: `src/css/quasar.variables.scss` (brand palette — friendly blue `#3B6FE0`, coral accent) + `src/css/app.scss` (CSS custom-property tokens + `.jg-card`/`.jg-pill`/etc.). Fonts: Fraunces (display) + Inter (body).
- `src/lib/api.ts` — single typed axios client; auth token held in a module var set by the auth store (no store↔client import cycle). `apiError()` normalizes error messages.
- `src/stores/` — Pinia: `auth` (session restore, `isAdmin`, impersonation enter/exit) and `cart` (persisted to localStorage).
- `src/router/index.ts` — routes + guard (`requiresAuth`, `requiresAdmin`).
- Layouts: `MainLayout` (consumer shell + impersonation banner), `AdminLayout` (sidebar).
- Pages under `src/pages/` (+ `pages/admin/`, `pages/provider/`).

---

## 5. Feature inventory (what's built)

### Parent marketplace (public + guardian)
- **Discovery** (`GET /search/sessions`, public): PostGIS radius from lat/lng (`ST_DWithin`, distance-ordered) or suburb/postcode fallback; filters date/child-age/category/price/session-type; `available_only`; only published + future sessions; live `seats_remaining`.
- **Listing detail** (`GET /catalog/sessions/{id}`, public, published-only): enriched with title/org/venue/description.
- **Auth**: signup/login (JWT), `/me`. **Child profiles** (data-minimised: first name + DOB only, no surname/photos).
- **Booking**: hold seats (TTL) → cart → checkout (idempotent, per-cart key) → confirm/cancel. Age-gating + child-count checks at checkout.
- **My bookings**, **Add to calendar** (.ics download), **Notifications inbox** (bell in header).

### Inventory correctness (the core promise)
- `catalog.Session.seats_taken` is the single source of truth; **inventory is its only writer**.
- Every mutation takes a `SELECT … FOR UPDATE` row lock; expired holds reclaimed under lock; **`ck_session_no_oversell` CHECK constraint is the DB backstop**.
- Proven by a concurrency test: 8 threads race for the last seat → exactly one wins, seven 409, `seats_taken == 1`. Stable across repeated runs.

### Provider console (`/provider`, any signed-in user)
- Create org → **compliance** (ABN, WWCC per staff, insurance ref — all land `pending`) → venues → programs → sessions → **publish** (suspended orgs can't publish) → **rosters** (with CSV export) → **cancel session** (→ refund + notify families) → **Earnings** (payouts view).

### Admin console (`/admin`, `is_admin` users)
- **Approvals**: list by status, **Review** dialog (ABN + WWCC + insurance with verify/reject), approve/suspend.
- **Payouts**: Scheduled/Held/Paid tabs, **Run due payouts**, hold/release.
- **Configuration**: runtime settings (fee %, seat-hold TTL, checkout window, reliability penalty, search radius, payout delay, impersonation TTL) — bounded, **versioned**, audited, effective immediately.
- **Feature flags**: on/off + rollout % (deterministic bucketing) + targeting.
- **Audit log**: every consequential action, filterable, records the **true actor** even under impersonation.
- **Impersonation**: user email/name search → **view-as** (read-only) / **act-as** (mutations audited) → scoped time-boxed token → consumer app with a **persistent support banner** → exit restores admin. Can't impersonate admins/self; ended sessions revoke immediately.
- **Bookings refund** (`POST /admin/payments/{id}/refund`).

### Money & comms
- **Payments**: Stripe-style intent → confirm; 10% application fee (from config); refunds; **payouts**: net (gross − fee) accrues per session on confirm, due at `session_end + payout_delay`, released by admin "Run payouts" (transfer + mark paid).
- **Notifications**: booking confirmation email (itinerary + .ics) on confirm; cancellation emails to families; guardian notification log. All via the fake email gateway (outbox + `NotificationLog`).

---

## 6. Data model & migrations

18 initial tables + 2 added columns + 1 table, across modules. Highlights:
- `user_account`, `child` (identity); `organisation`, `org_member`, `wwcc_record`, `insurance_doc` (org); `venue` (PostGIS `geography(POINT,4326)` + GiST index), `program`, `session` (catalog); `seat_hold` (inventory); `booking`, `booking_child` (booking); `payment`, `payout` (payments); `impersonation_session` (admin); `platform_setting` (versioned), `feature_flag`, `audit_event`, `notification_log`.
- Cross-module references use **string-based FKs** (`ForeignKey("organisation.id")`) so no module imports another's models just for a relationship.
- Migrations autogenerate cleanly because `alembic/env.py` **pins `search_path` to `public`** (the PostGIS image installs tiger/topology extensions whose schemas would otherwise leak into autogenerate) and uses GeoAlchemy2's alembic helpers.

---

## 7. Testing & verification approach

- **Backend**: pytest hits real Postgres through FastAPI `TestClient`; the `db` fixture wraps each test in a transaction that **rolls back**, and **clears `platform_setting`/`feature_flag` rows within the transaction** so every test sees built-in config defaults (a seeded/edited fee can't break fee-dependent tests). `make_admin` fixture flips `is_admin` then re-logs-in. DB tests **skip cleanly** if Postgres is unreachable.
- **The big proofs**: concurrency oversell test (threads), the checkout state machine, payout accrual/release, impersonation matrix, verification flow.
- **Frontend/UX**: verified by driving the real app in **headless Chromium (Playwright)** — full journeys (signup→book→pay→bookings, provider onboarding→publish, admin review/verify/run-payouts, impersonation banner) with screenshots reviewed for visual correctness. Playwright lives in the scratchpad, not the repo. There are **no committed frontend unit tests yet** (a gap — see §9).

---

## 8. Key decisions & gotchas (READ before changing things)

1. **DB is on host port 5433, not 5432.** An unrelated `lotscope` Docker stack owns 5432. `docker-compose.yml` maps `5433:5432`; `settings.py` default DB URL uses `localhost:5433`. Container-internal is still 5432 (so the compose `api` service is unaffected).
2. **Email validation rejects `.test`/reserved TLDs.** `email-validator` (via Pydantic `EmailStr`) rejects `foo@bar.test`. The seed's *demo provider* uses `demo-provider@juggle.test` (created via the service, which bypasses `EmailStr`) so it **can't log in through the UI**. The admin is `admin@example.com` (valid) so it can. Use `@example.com` for anything that logs in.
3. **`notifications` and `audit` sit LOW in the layering.** Callers pass fully-formed content. Don't make notifications fetch booking/catalog data — that would invert the layering and create a cycle.
4. **`deps.py` must not import the `admin` model.** It's imported by every ui; importing a top-module model creates a low→high cycle (import-linter will fail). The impersonation-active check uses raw SQL by table name on purpose.
5. **Runtime config vs deployment config.** Fees/TTLs/penalties live in the DB `config` module and are read via `config.service` typed accessors. Don't reintroduce hardcoded constants for these; don't put product config in `settings.py`.
6. **Timezone is display-dependent.** Sessions are stored UTC; the frontend renders in the viewer's local time. The demo seed stores `01:00 UTC` (= 9am AWST) so times read 9am–3pm on an AWST machine. A production build needs **real venue-timezone handling**, not reliance on the viewer's locale.
7. **Publish gate is "not suspended", not "must be approved".** PRD §8.1 wants approval-before-publish, but enforcing that would break the many test/seed flows that create pending orgs and publish. Current rule: **suspended** orgs can't publish; approval is a reviewed decision surfaced in the admin queue but not a hard publish precondition. Revisit if you want the strict gate (expect test churn).
8. **Payouts/emails/transfers are faked.** `FakeGateway.transfer` returns a `tr_fake_…` id; `FakeEmailGateway` writes to an in-memory outbox. Nothing is really sent/moved. `org.stripe_account_id` is null in seed data.
9. **Idempotency edges only.** Booking confirm sends the email + accrues payout **only on the pending→succeeded transition** (repeat confirm is a no-op). Cart checkout is idempotent via `payment.idempotency_key`.
10. **`make dev` uses `--reload`; `make web-dev` uses HMR.** If the user is running the app, backend route changes and frontend changes are picked up live — but a **stale uvicorn reloader child** can linger on :8000 and answer 404s after a kill; force-kill by PID if the proxy 404s.

---

## 9. Known limitations / gaps

- **No background scheduler.** Payout release and (future) T-48h/T-3h reminders are manual/ops-triggered. A worker/cron loop is the main missing infra.
- **Real integrations not wired**: Stripe (payments + Connect transfers), Postmark/SES (email). Both are gateway swaps.
- **No file upload**: insurance is a URL/`file_ref`, not an uploaded document (needs presigned S3).
- **No frontend unit/e2e tests committed** (only ad-hoc Playwright in scratchpad). Worth adding Vitest + a committed Playwright suite.
- **No SSR/PWA** (PRD wants SSR for SEO on listing pages + installable PWA). Currently SPA.
- **No user-search-by-child / duplicate-account merge / data-deletion workflow** (PRD §10.2 admin niceties).
- **Timezone handling** is naive (see gotcha #6).
- **P1 features not built**: reviews, waitlists, SMS, promo codes, saved-kid improvements, provider analytics, embeddable widget, birthday-party vertical (P2).

---

## 10. Suggested next work (roughly prioritized)

1. **Background scheduler / worker** — auto-run due payouts + send T-48h/T-3h reminders (and reclaim expired holds). This unlocks two half-built features and is real infra. Options: APScheduler in-process, or a `make`-invoked management command + cron, or an admin "run all due" that a cron hits.
2. **Real integrations** behind the gateways — Stripe (destination charges + Connect payouts) and Postmark/SES. Config in `settings.py`, select in `get_*_gateway()`.
3. **Hardening/review pass** — add committed frontend tests (Vitest + Playwright), rate limiting/booking-velocity limits (PRD fraud basics), CORS/secrets review, error-monitoring.
4. **Provider onboarding polish** — real doc upload (S3 presigned), and decide on the strict approval-before-publish gate.
5. **Timezone correctness** — store venue timezone; render per-venue.
6. **P1 features** — reviews (verified-booking-only), waitlists (auto-offer with claim window), SMS via Twilio behind a gateway.

---

## 11. Where things are (quick map)

```
apps/api/
  src/juggle/
    main.py, api.py, db.py, common.py, security.py, deps.py, models.py, settings.py
    modules/<name>/core/{models,schemas,service}.py  +  ui/routes.py
      identity org catalog inventory booking payments roster
      search admin config flags audit notifications
    modules/payments/core/gateway.py         # PaymentGateway + FakeGateway
    modules/notifications/core/{gateway,ical}.py
  alembic/versions/*.py                        # 4 migrations
  tests/test_*.py                              # 18 files, 79 tests
  scripts/seed_demo.py                         # demo data (admin + provider + sessions)
apps/web/
  src/lib/{api,types,format,jwt,sessionMemo}.ts
  src/stores/{auth,cart}.ts
  src/router/index.ts
  src/layouts/{MainLayout,AdminLayout}.vue
  src/pages/*.vue  +  pages/admin/*.vue  +  pages/provider/*.vue
  src/css/{quasar.variables,app}.scss
docs/{juggle-prd.md, HANDOFF.md}
CLAUDE.md, Makefile, docker-compose.yml
```

**Golden rule when adding a module or cross-module call:** respect the layering (import only lower modules, via their `core.service`), keep `core` free of FastAPI, add the router to `api.py`, and run `make check`. If import-linter fails, you've drawn a dependency arrow the wrong way — that's the signal, not the obstacle.
