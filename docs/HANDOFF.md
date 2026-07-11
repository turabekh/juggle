# Juggle — Session Handoff

_Last updated: 2026-07-11. Read this first, then `CLAUDE.md` (engineering conventions) and `docs/juggle-prd.md` (product spec)._

> **Latest slices (2026-07-11) — Phase-1, payments deferred per direction:**
> - **Reviews & trust (PRD §7.6):** `reviews` module — verified-booking-only, 1–5★ + text, moderation queue, provider right-of-reply, child-PII auto-screen, published-only aggregates; parent/provider/admin UI.
> - **Waitlist (PRD §7.7):** `waitlist` module — join a sold-out session, a freed seat is auto-offered to the FIFO front with a config-driven claim window (reserved via a seat hold), claim = normal checkout, expiry cascades; reconciliation runs lazily on reads + an admin ops sweep (no scheduler yet). Parent (join/claim) + provider (queue counts) UI. Browser-verified.
> - **Provider comms (PRD §8.5):** `comms` module — template-guarded broadcast to a session's confirmed families via the notifications gateway; records outbound history. (Automated T-24h "what to bring" deferred — needs the scheduler.)
> - **Provider analytics (PRD §8.6):** `analytics` module (no table) — fill rate, gross revenue, new-vs-returning family mix, per-program rollup. (Search impressions deferred — needs event instrumentation.) Both browser-verified.
>
> **17 domain modules** now; layering `admin ▸ analytics ▸ comms ▸ roster ▸ search ▸ reviews ▸ waitlist ▸ booking ▸ …`. See §5.

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

- **30 commits**, one per milestone/slice (see `git log --oneline`). All green at each step.
- **Backend: 109 pytest passing** (13 reviews + 10 waitlist + 4 comms + 3 analytics), mypy `--strict` clean, **import-linter 2/2 contracts KEPT**, ruff clean.
- **Frontend: vue-tsc + vite build clean.**
- **7 Alembic migrations**, head = `9aaf0095f9f4` (add_broadcast). Chain: initial → payment idempotency_key → booking seat_hold_id → notification_log → review → waitlist_entry → broadcast. The chain round-trips (down to base and back).
- **17 domain modules** (added `reviews`, `waitlist`, `comms`, `analytics`).
- Stack: FastAPI + SQLAlchemy 2 + PostgreSQL/PostGIS + Alembic (`apps/api`); Vite + Vue 3 (TS) + Quasar SPA (`apps/web`).

---

## 4. Architecture

### Backend module layering (enforced by import-linter)
17 domain modules under `apps/api/src/juggle/modules/`, each with a **`core/` (domain: models, schemas, service — NO FastAPI imports)** and **`ui/` (FastAPI router)** split. Two contracts in `pyproject.toml [tool.importlinter]`:

1. **`core` never imports FastAPI/Starlette.**
2. **Strict acyclic layering** (high→low — a module may import only modules **below** it):

   ```
   admin ▸ analytics ▸ comms ▸ roster ▸ search ▸ reviews ▸ waitlist ▸ booking ▸ payments ▸ inventory ▸ catalog ▸ org ▸ identity ▸ notifications ▸ flags ▸ config ▸ audit
   ```

   `analytics` (pure read rollup, no table) and `comms` (provider broadcasts) sit near the top with `roster` — both org-member-gated, both read down into `booking`/`catalog`; `comms` also fans out via `notifications`.

   `reviews` sits between `search` and `booking`: it verifies against a confirmed+completed `booking` (below it) and reads catalog/org/identity for enrichment; it has its own admin-gated moderation routes (no need for the top `admin` module to import it).

   `waitlist` sits between `reviews` and `booking`: it **reconciles against live inventory** rather than being pushed to — it reads booking/inventory/catalog/org/identity/notifications to offer freed seats, so the core checkout path is never modified. No booking→waitlist call exists (that would be an upward edge); offers surface via lazy reconciliation on reads + an admin ops sweep (`POST /waitlist/process`).

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
- **Reviews (P1, PRD §7.6)**: after a session finishes, **"Leave a review"** on the booking (1–5★ + text); the body is **auto-screened for the booking's child names** (blocked at submit — no child PII in content); reviews land in a **moderation queue** and only appear publicly once approved. **Listing detail** shows the program's published reviews + rating summary (with a "Verified booking" badge and any provider reply). One review per booking (DB `UNIQUE`); rating bound 1–5 by DB `CHECK`.
- **Waitlist (P1, PRD §7.7)**: on a **sold-out** listing, **"Join the waitlist"** (shows FIFO position). When a seat frees (a cancelled pending booking / admin refund), reconciliation **offers it to the front of the queue** by reserving the seat with a **claim-window hold** (config `waitlist_claim_window_minutes`, default 4h) and emailing the family; **"Claim your seat"** on *My bookings* books it via the normal checkout against that hold. Unclaimed offers **expire and cascade** to the next family. Providers see live **queue counts** on full sessions. FIFO uses a DB identity `seq` (stable even when `created_at` ties on the transaction clock); one active place per guardian/session (partial `UNIQUE`).

### Inventory correctness (the core promise)
- `catalog.Session.seats_taken` is the single source of truth; **inventory is its only writer**.
- Every mutation takes a `SELECT … FOR UPDATE` row lock; expired holds reclaimed under lock; **`ck_session_no_oversell` CHECK constraint is the DB backstop**.
- Proven by a concurrency test: 8 threads race for the last seat → exactly one wins, seven 409, `seats_taken == 1`. Stable across repeated runs.

### Provider console (`/provider`, any signed-in user)
- Create org → **compliance** (ABN, WWCC per staff, insurance ref — all land `pending`) → venues → programs → sessions → **publish** (suspended orgs can't publish) → **rosters** (with CSV export) → **cancel session** (→ refund + notify families) → **Earnings** (payouts view).
- **Message families (P1, PRD §8.5)**: per-session **broadcast** — a template-guarded dialog (What to bring / Reminder / Update / Custom presets) sends to every confirmed family via the notifications gateway and records outbound history; recipient count reported. No free-text parent↔provider chat (PRD §8.5).
- **Insights (P1, PRD §8.6)**: org **analytics** — seats-filled %, gross bookings revenue, new-vs-returning family mix, and a per-program fill-rate + revenue rollup. Full sessions also show live **waitlist queue counts**.

### Admin console (`/admin`, `is_admin` users)
- **Approvals**: list by status, **Review** dialog (ABN + WWCC + insurance with verify/reject), approve/suspend.
- **Payouts**: Scheduled/Held/Paid tabs, **Run due payouts**, hold/release.
- **Configuration**: runtime settings (fee %, seat-hold TTL, checkout window, reliability penalty, search radius, payout delay, impersonation TTL) — bounded, **versioned**, audited, effective immediately.
- **Feature flags**: on/off + rollout % (deterministic bucketing) + targeting.
- **Audit log**: every consequential action, filterable, records the **true actor** even under impersonation.
- **Impersonation**: user email/name search → **view-as** (read-only) / **act-as** (mutations audited) → scoped time-boxed token → consumer app with a **persistent support banner** → exit restores admin. Can't impersonate admins/self; ended sessions revoke immediately.
- **Bookings refund** (`POST /admin/payments/{id}/refund`).
- **Review moderation** (`/admin/reviews`): pending/published/rejected queue; **approve** (→published) / **reject-with-reason** (audited). Providers reply from their org console; published reviews aggregate to a provider/program rating.

### Money & comms
- **Payments**: Stripe-style intent → confirm; 10% application fee (from config); refunds; **payouts**: net (gross − fee) accrues per session on confirm, due at `session_end + payout_delay`, released by admin "Run payouts" (transfer + mark paid).
- **Notifications**: booking confirmation email (itinerary + .ics) on confirm; cancellation emails to families; guardian notification log. All via the fake email gateway (outbox + `NotificationLog`).

---

## 6. Data model & migrations

18 initial tables + 2 added columns + 4 tables (`notification_log`, `review`, `waitlist_entry`, `broadcast`), across modules. Highlights:
- `user_account`, `child` (identity); `organisation`, `org_member`, `wwcc_record`, `insurance_doc` (org); `venue` (PostGIS `geography(POINT,4326)` + GiST index), `program`, `session` (catalog); `seat_hold` (inventory); `booking`, `booking_child` (booking); `payment`, `payout` (payments); `review` (reviews — `UNIQUE(booking_id)`, `CHECK(rating 1..5)`, native `review_status` enum); `waitlist_entry` (waitlist — identity `seq` for FIFO, partial `UNIQUE` on active status per guardian/session); `impersonation_session` (admin); `platform_setting` (versioned), `feature_flag`, `audit_event`, `notification_log`.
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

**Direction (2026-07-11): payments work is deferred; focus on Phase-1 product.** Reviews (§7.6), Waitlist (§7.7), and provider Comms + Analytics (§8.5/§8.6) are done. The next payment-free P1 slices:

1. **Background scheduler / worker** — the payment-free half is now well-motivated: **automated "what to bring" T-24h** (comms, deferred here), **T-48h/T-3h reminders**, the **waitlist offer-expiry sweep** (`POST /waitlist/process` is already cron-ready), and reclaiming expired holds. A single periodic worker unlocks several half-built features. Payout release is the payment-touching half.
2. **Saved-kids / multi-guardian polish (§7.3 P1)**, **attendance check-in (§8.3 "tap to mark attended")** — small, self-contained.
3. **Search-impression / funnel instrumentation (§13)** — the event taxonomy is specced; would complete the analytics "search impressions" gap.

Deferred (need payments or external integrations, revisit later):
- **Payout release** side of the scheduler (payment-touching).
- **Real integrations** behind the gateways — Stripe (destination charges + Connect payouts), Postmark/SES email, SMS via Twilio.
- **Provider doc upload** (S3 presigned) + strict approval-before-publish gate; **timezone correctness** (store venue tz); refund automation, promo codes.

Cross-cutting, do anytime: **committed frontend tests** (Vitest + Playwright), rate limiting/booking-velocity limits, CORS/secrets review, error monitoring.

---

## 11. Where things are (quick map)

```
apps/api/
  src/juggle/
    main.py, api.py, db.py, common.py, security.py, deps.py, models.py, settings.py
    modules/<name>/core/{models,schemas,service}.py  +  ui/routes.py
      identity org catalog inventory booking payments roster
      search reviews waitlist comms analytics admin config flags audit notifications
    modules/payments/core/gateway.py         # PaymentGateway + FakeGateway
    modules/notifications/core/{gateway,ical}.py
  alembic/versions/*.py                        # 7 migrations
  tests/test_*.py                              # 22 files, 109 tests
  scripts/seed_demo.py                         # demo data (admin + provider + sessions + reviews + waitlist)
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
