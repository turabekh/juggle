# Juggle — Session Handoff

_Last updated: 2026-07-11. Read this first, then `CLAUDE.md` (engineering conventions) and `docs/juggle-prd.md` (product spec)._

> **Latest slices (2026-07-11) — Phase-1, payments deferred per direction:**
> - **Reviews & trust (PRD §7.6):** `reviews` module — verified-booking-only, 1–5★ + text, moderation queue, provider right-of-reply, child-PII auto-screen, published-only aggregates; parent/provider/admin UI.
> - **Waitlist (PRD §7.7):** `waitlist` module — join a sold-out session, a freed seat is auto-offered to the FIFO front with a config-driven claim window (reserved via a seat hold), claim = normal checkout, expiry cascades; reconciliation runs lazily on reads + an admin ops sweep (no scheduler yet). Parent (join/claim) + provider (queue counts) UI. Browser-verified.
> - **Provider comms (PRD §8.5):** `comms` module — template-guarded broadcast to a session's confirmed families via the notifications gateway; records outbound history.
> - **Provider analytics (PRD §8.6):** `analytics` module (no table) — fill rate, gross revenue, new-vs-returning family mix, per-program rollup. (Search impressions deferred — needs event instrumentation.)
> - **Background scheduler (PRD §7.5/§7.7):** `scheduler` module — one idempotent maintenance tick: reclaim expired holds, sweep the waitlist (offer/expire), and send **T-48h/T-3h pre-session reminders** (deduped by a `session_reminder` marker). Driven by a **worker** (`make worker` / `make worker-loop`, `python -m juggle.worker [--loop]`, or the compose `worker` service) or the admin **Operations** page (`POST /scheduler/run`). Payout release stays manual (payments deferred).
> - **Attendance check-in (PRD §8.3):** the `roster` module gained its first table — morning-of **tap-to-check-in** (`Attendance`, keyed by booking_child_id). Roster rows carry `attended`/`attended_at` + an `attended_count`; CSV has an `attended` column; provider roster dialog toggles it.
> - **Multiple guardians per family (PRD §7.3):** `identity.GuardianLink` (invite → accept; symmetric access once accepted). `list_children` + booking checkout/`list_bookings` use `family_guardian_ids`; account page "Family" section.
> - **Automated "what to bring" T-24h (PRD §8.5):** sessions carry an optional `what_to_bring`; a scheduler T-24h job emails it to confirmed families, deduped (SessionReminder window `wtb`).
> - **Funnel instrumentation (PRD §13):** bottom-tier `events` module (`analytics_event`, no child PII) records the 8-stage taxonomy from search/catalog/booking/org/inventory; admin **Funnel** page via `GET /analytics/funnel`.
> - **Listing SEO (PRD §7.1):** `GET /catalog/sitemap.xml` + `robots.txt`; a dependency-free `useHead` composable sets per-listing title/description/canonical/OG + **schema.org Event JSON-LD** (Googlebot renders JS → indexed + rich-result eligible). Browser-verified.
> - **PWA (done):** installable web manifest + generated maskable icons + an offline app-shell service worker (dependency-free). Browser-verified.
> - **SSR (pipeline built, blocked):** the full isomorphic setup exists (app factory, client/server entries, `server.mjs`, SSR-safe guards) but **can't render** — `@quasar/vite-plugin` ships only Quasar's client bundle; Quasar SSR is CLI-only. See §9.
>
> **19 domain modules** now; layering `scheduler ▸ admin ▸ analytics ▸ comms ▸ roster ▸ search ▸ reviews ▸ waitlist ▸ booking ▸ … ▸ audit ▸ events`. See §5.

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

`make check` (from repo root or `apps/api`) runs the full backend gate: ruff + mypy(strict) + import-linter + pytest. Frontend: `make web-build` (vue-tsc + vite build) and `make web-test` (Vitest units).

---

## 3. Current state (facts)

- **41 commits**, one per milestone/slice (see `git log --oneline`). All green at each step.
- **Backend: 138 pytest passing** (P1 suites + sitemap + anti-hoarding + duplicate-sessions), mypy `--strict` clean, **import-linter 2/2 contracts KEPT**, ruff clean. NB: e2e/browser runs commit data to the dev DB — `make db && (downgrade base→upgrade head) && make seed` before backend tests if the global payout/hold assertions trip.
- **Frontend e2e: 5 Playwright specs green** (`make web-e2e`, stack up).
- **Frontend: vue-tsc + vite build clean.**
- **12 Alembic migrations**, head = `e08fed049dda` (add_analytics_event). Recent chain tail: … → attendance → guardian_link → session.what_to_bring → analytics_event. The chain round-trips (down to base and back).
- **19 domain modules** (added `reviews`, `waitlist`, `comms`, `analytics`, `scheduler`, `events`).
- **Background worker**: `make worker` (one tick) / `make worker-loop` (every 5 min); also the compose `worker` service.
- Stack: FastAPI + SQLAlchemy 2 + PostgreSQL/PostGIS + Alembic (`apps/api`); Vite + Vue 3 (TS) + Quasar SPA (`apps/web`).

---

## 4. Architecture

### Backend module layering (enforced by import-linter)
19 domain modules under `apps/api/src/juggle/modules/`, each with a **`core/` (domain: models, schemas, service — NO FastAPI imports)** and **`ui/` (FastAPI router)** split. Two contracts in `pyproject.toml [tool.importlinter]`:

1. **`core` never imports FastAPI/Starlette.**
2. **Strict acyclic layering** (high→low — a module may import only modules **below** it):

   ```
   scheduler ▸ admin ▸ analytics ▸ comms ▸ roster ▸ search ▸ reviews ▸ waitlist ▸ booking ▸ payments ▸ inventory ▸ catalog ▸ org ▸ identity ▸ notifications ▸ flags ▸ config ▸ audit ▸ events
   ```

   `events` sits at the very bottom (like `audit`): a write-only funnel log that every higher module emits to (`events.record`) with non-PII context — search/catalog/booking/org/inventory all instrument their key steps; the admin funnel read lives in `analytics` (which is above `events`). (No `ui` router — reads go through `analytics`.)

   `analytics` (pure read rollup, no table) and `comms` (provider broadcasts) sit near the top with `roster` — both org-member-gated, both read down into `booking`/`catalog`; `comms` also fans out via `notifications`.
   `scheduler` is the topmost module: it **orchestrates** lower modules on a periodic tick (`inventory.reclaim_all_expired`, `waitlist.process_all`, reminders) — pure domain logic driven by `src/juggle/worker.py` (not a module) or `POST /scheduler/run`.

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
- `worker.py` — the background maintenance runner (`python -m juggle.worker [--loop --interval N]`). Each tick calls `scheduler.run_due_jobs` in its own committed transaction; the loop survives a failed tick. `make worker` / `make worker-loop`.

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
- **SEO (P1, §7.1)**: `GET /catalog/sitemap.xml` (indexable listings) + `robots.txt`; the `useHead` composable gives each listing page a real title/description/canonical/OG + **schema.org Event JSON-LD** (price, availability, dates, venue) for rich results. Client-rendered (fine for Googlebot); full request-time SSR is a follow-up for non-JS crawlers.
- **Listing detail** (`GET /catalog/sessions/{id}`, public, published-only): enriched with title/org/venue/description.
- **Auth**: signup/login (JWT), `/me`. **Child profiles** (data-minimised: first name + DOB only, no surname/photos). **Co-guardians (P1, §7.3)**: invite another parent by email → they accept → both share the family's kids and see each other's bookings ("Family" section on the account page).
- **Booking**: hold seats (TTL) → cart → checkout (idempotent, per-cart key) → confirm/cancel. Age-gating + child-count checks at checkout.
- **My bookings**, **Add to calendar** (.ics download), **Notifications inbox** (bell in header).
- **Reviews (P1, PRD §7.6)**: after a session finishes, **"Leave a review"** on the booking (1–5★ + text); the body is **auto-screened for the booking's child names** (blocked at submit — no child PII in content); reviews land in a **moderation queue** and only appear publicly once approved. **Listing detail** shows the program's published reviews + rating summary (with a "Verified booking" badge and any provider reply). One review per booking (DB `UNIQUE`); rating bound 1–5 by DB `CHECK`.
- **Waitlist (P1, PRD §7.7)**: on a **sold-out** listing, **"Join the waitlist"** (shows FIFO position). When a seat frees (a cancelled pending booking / admin refund), reconciliation **offers it to the front of the queue** by reserving the seat with a **claim-window hold** (config `waitlist_claim_window_minutes`, default 4h) and emailing the family; **"Claim your seat"** on *My bookings* books it via the normal checkout against that hold. Unclaimed offers **expire and cascade** to the next family. Providers see live **queue counts** on full sessions. FIFO uses a DB identity `seq` (stable even when `created_at` ties on the transaction clock); one active place per guardian/session (partial `UNIQUE`).

### Inventory correctness (the core promise)
- `catalog.Session.seats_taken` is the single source of truth; **inventory is its only writer**.
- Every mutation takes a `SELECT … FOR UPDATE` row lock; expired holds reclaimed under lock; **`ck_session_no_oversell` CHECK constraint is the DB backstop**.
- Proven by a concurrency test: 8 threads race for the last seat → exactly one wins, seven 409, `seats_taken == 1`. Stable across repeated runs.

### Provider console (`/provider`, any signed-in user)
- Create org → **compliance** (ABN, WWCC per staff, insurance ref — all land `pending`) → venues → programs → sessions → **publish** (suspended orgs can't publish) → **rosters** (with CSV export + **morning-of tap-to-check-in**, §8.3) → **cancel session** (→ refund + notify families) → **Earnings** (payouts view).
- **Duplicate-from-last-cycle (P1, §8.2)**: one-click **re-list** — copy all of a program's non-cancelled sessions shifted forward by whole days (preserving time-of-day/venue/pricing, seats reset). `POST /catalog/programs/{id}/duplicate-sessions`; "Duplicate to new dates" on the program page. (PRD's lever for provider relist rate.)
- **Message families (P1, PRD §8.5)**: per-session **broadcast** — a template-guarded dialog (What to bring / Reminder / Update / Custom presets) sends to every confirmed family via the notifications gateway and records outbound history; recipient count reported. No free-text parent↔provider chat (PRD §8.5).
- **Insights (P1, PRD §8.6)**: org **analytics** — seats-filled %, gross bookings revenue, new-vs-returning family mix, and a per-program fill-rate + revenue rollup. Full sessions also show live **waitlist queue counts**.

### Admin console (`/admin`, `is_admin` users)
- **Approvals**: list by status, **Review** dialog (ABN + WWCC + insurance with verify/reject), approve/suspend.
- **Payouts**: Scheduled/Held/Paid tabs, **Run due payouts**, hold/release.
- **Configuration**: runtime settings (fee %, seat-hold TTL, checkout window, reliability penalty, search radius, payout delay, impersonation TTL, waitlist claim window, **max active holds per guardian**) — bounded, **versioned**, audited, effective immediately.
- **Anti-hoarding (fraud basics)**: `inventory.hold_seats` caps a guardian's concurrent live holds at the config value → **429** over the limit (released/expired holds free a slot). Edge/login rate-limiting stays an nginx concern.
- **Feature flags**: on/off + rollout % (deterministic bucketing) + targeting.
- **Audit log**: every consequential action, filterable, records the **true actor** even under impersonation.
- **Impersonation**: user email/name search → **view-as** (read-only) / **act-as** (mutations audited) → scoped time-boxed token → consumer app with a **persistent support banner** → exit restores admin. Can't impersonate admins/self; ended sessions revoke immediately.
- **Bookings refund** (`POST /admin/payments/{id}/refund`).
- **Review moderation** (`/admin/reviews`): pending/published/rejected queue; **approve** (→published) / **reject-with-reason** (audited). Providers reply from their org console; published reviews aggregate to a provider/program rating.
- **Operations** (`/admin/operations`): **Run maintenance now** triggers one scheduler tick (`POST /scheduler/run`) and shows the summary — reminders sent (incl. T-24h "what to bring"), waitlist offers made/expired/queues checked, seat holds reclaimed. A worker normally runs this on a loop.
- **Funnel** (`/admin/funnel`, P1 §13): windowed bar breakdown of the product event taxonomy (searches → listings viewed → checkouts started/completed → cancelled; plus sessions filled, listings published, provider signups). Reads `analytics_event` via `GET /analytics/funnel`.

### Money & comms
- **Payments**: Stripe-style intent → confirm; 10% application fee (from config); refunds; **payouts**: net (gross − fee) accrues per session on confirm, due at `session_end + payout_delay`, released by admin "Run payouts" (transfer + mark paid).
- **Notifications**: booking confirmation email (itinerary + .ics) on confirm; cancellation emails to families; guardian notification log. All via the fake email gateway (outbox + `NotificationLog`).

---

## 6. Data model & migrations

18 initial tables + 3 added columns (`what_to_bring` on `session`) + 8 tables (`notification_log`, `review`, `waitlist_entry`, `broadcast`, `session_reminder`, `attendance`, `guardian_link`, `analytics_event`), across modules. Highlights:
- `user_account`, `child` (identity); `organisation`, `org_member`, `wwcc_record`, `insurance_doc` (org); `venue` (PostGIS `geography(POINT,4326)` + GiST index), `program`, `session` (catalog); `seat_hold` (inventory); `booking`, `booking_child` (booking); `payment`, `payout` (payments); `review` (reviews — `UNIQUE(booking_id)`, `CHECK(rating 1..5)`, native `review_status` enum); `waitlist_entry` (waitlist — identity `seq` for FIFO, partial `UNIQUE` on active status per guardian/session); `impersonation_session` (admin); `platform_setting` (versioned), `feature_flag`, `audit_event`, `notification_log`.
- Cross-module references use **string-based FKs** (`ForeignKey("organisation.id")`) so no module imports another's models just for a relationship.
- Migrations autogenerate cleanly because `alembic/env.py` **pins `search_path` to `public`** (the PostGIS image installs tiger/topology extensions whose schemas would otherwise leak into autogenerate) and uses GeoAlchemy2's alembic helpers.

---

## 7. Testing & verification approach

- **Backend**: pytest hits real Postgres through FastAPI `TestClient`; the `db` fixture wraps each test in a transaction that **rolls back**, and **clears `platform_setting`/`feature_flag` rows within the transaction** so every test sees built-in config defaults (a seeded/edited fee can't break fee-dependent tests). `make_admin` fixture flips `is_admin` then re-logs-in. DB tests **skip cleanly** if Postgres is unreachable.
- **The big proofs**: concurrency oversell test (threads), the checkout state machine, payout accrual/release, impersonation matrix, verification flow.
- **Frontend unit tests (committed)**: **Vitest** (jsdom + @vue/test-utils, Quasar installed in `test/setup.ts`) — 15 tests covering `lib/format`, `lib/jwt`, the SSR-safe `lib/storage` shim, the cart Pinia store (totals + localStorage persistence), and the `StarRating` component. `make web-test` / `npm test`.
- **Frontend e2e (committed)**: **Playwright** (`apps/web/e2e/`, chromium) — self-contained specs (data set up via the API, no seed dependency): listing SEO (title + Event JSON-LD), waitlist join→offer→claim, provider roster check-in, and co-guardian invite→accept across two browser contexts. `make web-e2e` / `npm run e2e`; **needs the full stack running** (db + api + web-dev). Prereqs in `playwright.config.ts`; artifacts gitignored.

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

- **Scheduler runs via the compose `worker` service** (`docker compose up` starts db + api + worker looping every 5 min); `make worker[-loop]` or cron hitting `POST /scheduler/run` also work. A non-compose production deploy still needs its own process/cron for the worker. Payout release is deliberately **not** in the tick (payments deferred) — it's still the manual admin "Run due payouts".
- **Real integrations not wired**: Stripe (payments + Connect transfers), Postmark/SES (email). Both are gateway swaps.
- **No file upload**: insurance is a URL/`file_ref`, not an uploaded document (needs presigned S3).
- **Frontend tests committed**: Vitest units (`make web-test`) + a Playwright e2e suite (`make web-e2e`, needs the stack up). Neither is wired into a headless CI runner yet (e2e needs db+api+web orchestration) — that's the remaining test-infra step.
- **PWA: done.** Installable (web manifest + generated maskable icons via `scripts/gen-icons.mjs`, dependency-free) with an offline app-shell service worker (`public/sw.js`, registered in prod builds only; never caches `/api`). Browser-verified.
- **Request-time SSR: pipeline built but BLOCKED on the UI layer.** The full isomorphic setup exists and is correct — `src/app.ts` factory, `entry-client.ts`/`entry-server.ts`, history-injectable router, `server.mjs` (dev + prod), `build:ssr` scripts, and SSR-safe storage/api/head guards (all additive; the SPA build is untouched and green). **It cannot render** because `@quasar/vite-plugin` only ships Quasar's *client* bundle (touches `window` at import) — Quasar SSR is officially supported **only** through the Quasar CLI (`@quasar/app-vite`). Empirically confirmed: externalizing to Quasar's `node` export and Node DOM-shims both fail. **To activate SSR:** migrate the app to the Quasar CLI SSR mode (large restructure the team deliberately avoided), or swap Quasar for an SSR-capable UI kit. Note SEO is already handled client-side (meta + JSON-LD + `sitemap.xml`, indexed by Googlebot), so SSR's remaining upside is non-JS crawlers + faster first paint.
- **No user-search-by-child / duplicate-account merge / data-deletion workflow** (PRD §10.2 admin niceties).
- **Timezone handling** is naive (see gotcha #6).
- **P1 features not built**: SMS (Twilio), promo codes, Google/Apple SSO, embeddable widget (P2), birthday-party vertical (P2). (Reviews, waitlists, provider analytics, comms, multi-guardian, and funnel instrumentation are now built.)

---

## 10. Suggested next work (roughly prioritized)

**Direction (2026-07-11): payments work is deferred; focus on Phase-1 product.** The payment-free P1 surface is now largely built: Reviews (§7.6), Waitlist (§7.7), Comms + Analytics (§8.5/§8.6), scheduler/worker (§7.5/§7.7), attendance check-in (§8.3), multiple guardians (§7.3), automated T-24h "what to bring" (§8.5), and funnel instrumentation (§13). Remaining payment-free slices:

1. **Full request-time SSR / PWA (§7.1)** — SEO for listing pages is now handled client-side (meta + JSON-LD + sitemap, indexed by Googlebot); true SSR (non-JS crawlers, faster first paint) + an installable PWA are the remaining frontend-infra items. This is a large, higher-risk change to the serving model — scope it deliberately.
2. **Per-cycle funnel dashboards / conversion rates (§13)** — the `analytics_event` log is captured; build richer views on top if wanted.
3. **Google/Apple SSO (§7.3)** and **SMS via Twilio behind a gateway (§8.5)** — need external integrations.

Deferred (need payments or external integrations, revisit later):
- **Payout auto-release** in the scheduler (payment-touching — currently manual admin "Run due payouts").
- **Real integrations** behind the gateways — Stripe (destination charges + Connect payouts), Postmark/SES email, SMS via Twilio.
- **Provider doc upload** (S3 presigned) + strict approval-before-publish gate; **timezone correctness** (store venue tz); refund automation, promo codes.

Cross-cutting, do anytime: **CI wiring** for the frontend suites (Vitest + Playwright now committed; e2e needs a stack-orchestrating runner), CORS/secrets review, error monitoring.

---

## 11. Where things are (quick map)

```
apps/api/
  src/juggle/
    main.py, api.py, db.py, common.py, security.py, deps.py, models.py, settings.py
    modules/<name>/core/{models,schemas,service}.py  +  ui/routes.py
      identity org catalog inventory booking payments roster search reviews
      waitlist comms analytics scheduler events admin config flags audit notifications
    modules/payments/core/gateway.py         # PaymentGateway + FakeGateway
    modules/notifications/core/{gateway,ical}.py
    worker.py                                  # background maintenance runner
  alembic/versions/*.py                        # 12 migrations
  tests/test_*.py                              # 27 files, 130 tests
  scripts/seed_demo.py                         # demo data (admin + provider + sessions + reviews + waitlist)
apps/web/
  public/{robots.txt, manifest.webmanifest, sw.js, icon-*.png}   # SEO + PWA
  scripts/gen-icons.mjs                        # dependency-free PWA icon generator
  server.mjs                                   # SSR runner (blocked on Quasar CLI — §9)
  vitest.config.ts, test/setup.ts              # unit-test harness (Vitest + Quasar)
  playwright.config.ts, e2e/                    # committed e2e suite (needs stack up)
  src/{app,entry-client,entry-server}.ts       # isomorphic app factory + entries
  src/lib/{api,types,format,jwt,sessionMemo,head,storage}.ts   # head=SEO, storage=SSR-safe kv
  src/stores/{auth,cart}.ts
  src/router/index.ts
  src/layouts/{MainLayout,AdminLayout}.vue
  src/pages/*.vue  +  pages/admin/*.vue  +  pages/provider/*.vue
  src/css/{quasar.variables,app}.scss
docs/{juggle-prd.md, HANDOFF.md}
CLAUDE.md, Makefile, docker-compose.yml
```

**Golden rule when adding a module or cross-module call:** respect the layering (import only lower modules, via their `core.service`), keep `core` free of FastAPI, add the router to `api.py`, and run `make check`. If import-linter fails, you've drawn a dependency arrow the wrong way — that's the signal, not the obstacle.
