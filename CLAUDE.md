# CLAUDE.md

Context for Claude Code working in this repository. Read it before making changes, and keep it up to date as the project evolves.

## Project overview

**Juggle** (working title) is a two-sided **booking marketplace for kids' school-holiday activities and birthday parties**, launching in Perth, Australia. It has:

- a **parent-facing marketplace** — search by suburb/date/child-age, live seat availability, one-cart multi-provider checkout, manage bookings;
- **free SaaS-lite tools for providers** — self-serve listings, session/capacity management, live roster, Stripe payouts (this is both the supply hook and the source of live availability);
- a **first-class admin console** — runtime config, provider approval/verification, bookings ops, incident register, and `view-as`/`act-as` impersonation.

The full product spec — requirement IDs, phasing, edge cases, acceptance criteria — is in **`docs/juggle-prd.md`**. It is the source of truth; this file is the engineering orientation on top of it.

> **Status:** Pre-gate per the PRD (build is contingent on the August provider-sprint kill criteria). Progress: scaffold + **M1** (data model), **M2** (identity auth, guardian/child, provider orgs), **M3** (catalog + inventory: sessions + oversell-proof seat holds), **M4** (search: public PostGIS radius + filters), and **M5** (booking checkout: holds→pending→confirmed/cancelled state machine, cart-level idempotency, 10% application fee, age gating, via a `PaymentGateway` interface with a `FakeGateway` — real Stripe drops in behind it). **M6** (roster + provider cancellation), and **M7a** (config: versioned/bounded/audit-logged runtime settings with the fee %, seat-hold TTL, checkout window, and reliability penalty now sourced from config instead of hardcoded; flags: on/off + rollout + targeting; audit: append-only trail; all admin-gated). and **M7b** (admin: provider approve/suspend with a publish gate for suspended orgs; bookings-console refund; impersonation view-as/act-as via a scoped token carrying the true actor, with read-only enforcement, per-action audit, no admin escalation, and immediate revoke on end). **All 13 module routers are live**, and **M8** (Quasar parent marketplace: discovery/search → listing detail → hold → cart → checkout → bookings, with auth, "my kids", persisted cart; verified end-to-end through the Vite proxy against seeded data). Backend MVP core + a wired frontend are done. **Phase-1 (post-MVP) work is well underway: `reviews` (§7.6, verified-booking reviews + moderation), `waitlist` (§7.7, join sold-out → auto-offer a freed seat with a config-driven claim window → claim via normal checkout), `comms` (§8.5, template-guarded provider broadcasts), `analytics` (§8.6, provider fill-rate/revenue/family-mix rollup), a `scheduler` (§7.5/§7.7 — one idempotent maintenance tick: reclaim expired holds + waitlist offer/expiry sweep + T-48h/T-3h reminders + automated T-24h "what to bring", run by `src/juggle/worker.py` / `make worker[-loop]` / the compose `worker` service / the admin Operations page), **attendance check-in** (§8.3 — the `roster` module's `Attendance` table), **multiple guardians per family** (§7.3 — `identity.GuardianLink`, invite→accept, shared kids + bookings), **funnel instrumentation** (§13 — the bottom-tier `events` module records the product event taxonomy; admin Funnel page reads it via `analytics`), **listing SEO** (§7.1 — sitemap + `useHead` meta + schema.org Event JSON-LD; PWA done, request-time SSR blocked on Quasar-CLI), and a further trust/ops/scheduling batch — **verification badges** (§7.2), **APP data-deletion** (§10.2), **compliance-expiry auto-tracking** (§8.1), **listing Q&A** (§7.2 `qanda` module), **duplicate + bulk session scheduling** (§8.2), plus **anti-hoarding hold caps** and committed **Vitest + Playwright** suites. 20 modules, all with the relevant UI.** **PWA is done** (installable + offline SW); a full **SSR pipeline is built but blocked** on `@quasar/vite-plugin` shipping only Quasar's client bundle (SSR needs a Quasar-CLI migration — see HANDOFF §9). **The Payments track (Stripe Connect) is now greenlit and underway** (reverses the earlier deferral): **F-PAY-0** (decisions + ADRs 0001–0005: separate charges & transfers, 10% fee-exclusive + GST per-session rounding, absorbed surcharge, T+2 payouts, checkout-settlement redesign) **F-PAY-1** (provider Connect Express onboarding + `account.updated` webhook syncing capability flags via the `stripe_event` idempotency ledger + payout gating on `payouts_enabled`; provider org-page payouts-setup UI), and **F-PAY-2** (checkout settlement: GST-correct take-rate per ADR-0002 — `gst_rate` config, `net = line − fee − gst`, per-session rounding, `Payment.fee_gst_cents`; **firm reservation** per ADR-0005 — `SeatHoldStatus.reserved` seats are committed and not TTL-reclaimed, reserved before the Stripe call; the **abandoned-checkout sweep** in the scheduler tick frees seats + fails the order past `checkout_window`; seat/payment transitions are row-locked against concurrent releasers), and **F-PAY-3** (webhook-driven confirmation: the single Stripe webhook sink is **`POST /api/v1/booking/stripe/webhook`** — hosted in `booking` because settlement orchestrates it, with `payments` exposing verify/dedupe/account primitives; `payment_intent.succeeded` confirms if the reservation is still firm else **auto-refunds the lost seat**, `.canceled` releases, `.payment_failed` is non-terminal; all idempotent via the `stripe_event` ledger; the synchronous `confirm()` endpoint is now gated to the fake gateway — 409 under live Stripe) are complete. Real Stripe lives behind the `PaymentGateway` Protocol (see table). **Next: F-PAY-4/5/6** — provider-cancellation refund automation (INV-5) with **payout clawback / Stripe Transfer Reversal**, payout release hardening (SKIP LOCKED + per-payout idempotency key + per-item commit), and the GST tax invoice. Remaining gaps: those + real email integration, Google/Apple SSO, SMS. Confirm milestone scope before implementing.

> **Runtime config:** operational levers (fee %, TTLs, penalties) live in the DB via the `config` module and are read through `config.service` typed accessors — do NOT reintroduce hardcoded constants for these. Admin auth uses `get_current_admin` (JWT `is_admin` claim); there is no admin-creation endpoint yet (set `user_account.is_admin` directly / via seed).

> **Name:** "Juggle" is a placeholder pending an ASIC/trademark check (PRD D-01). The Python package is `juggle`. If the name changes, update the PRD, this file, the package, and `docker-compose.yml`.

## Tech stack

| Concern | Choice |
| --- | --- |
| Backend | FastAPI (Python 3.12+), managed with `uv` |
| Database | PostgreSQL + **PostGIS** (geo search); SQLAlchemy 2 + Alembic |
| Frontend | Vite + Vue 3 (TS) + Quasar SPA (`apps/web`). **PWA done** (manifest + offline SW). **SSR pipeline built but blocked** — `@quasar/vite-plugin` ships only Quasar's client bundle, so SSR needs a Quasar-CLI migration to activate (see HANDOFF §9). `make web-dev` (proxies `/api`→:8000) |
| Payments | Stripe Connect Express, **separate charges & transfers** (platform is merchant of record; per-session `Transfer` at T+2) — see ADR-0001. Behind a `PaymentGateway` Protocol; `StripeGateway` activates only when `JUGGLE_STRIPE_SECRET_KEY` is set, else `FakeGateway` |
| Notifications | Transactional email (Postmark/SES) MVP; SMS (Twilio) is P1 |
| Module boundaries | **import-linter** contracts (core/ui split) |
| Lint / types | ruff + mypy (strict) |
| Tests | pytest + httpx TestClient |
| Local infra | Docker Compose (Postgres/PostGIS + API) |

If you change any of these, update this table.

## Repository layout

```
jungler/
├── docs/juggle-prd.md          # product spec — source of truth
├── docker-compose.yml          # db (postgis) + api
├── Makefile                    # dev shortcuts (make help)
├── .env.example                # deployment config template (JUGGLE_ prefix)
├── apps/
│   ├── api/                    # FastAPI backend
│   │   ├── pyproject.toml       # deps, ruff/mypy/pytest, import-linter contracts
│   │   ├── Dockerfile
│   │   ├── alembic.ini, alembic/
│   │   ├── src/juggle/
│   │   │   ├── main.py          # app factory + /health
│   │   │   ├── api.py           # aggregates module routers under /api/v1
│   │   │   ├── settings.py      # deployment config (env)
│   │   │   ├── db.py            # engine, session, Base
│   │   │   └── modules/<name>/  # one package per PRD §12 module
│   │   │       ├── core/        # domain: models.py, service.py  (NO web imports)
│   │   │       └── ui/          # routes.py (FastAPI router)
│   │   └── tests/
│   └── web/                    # Quasar PWA (placeholder — see its README)
└── CLAUDE.md
```

## Architecture & conventions

- **Modules (PRD §12):** `identity, org, catalog, inventory, booking, payments, roster, notifications, search, reviews, qanda, waitlist, comms, analytics, scheduler, events, admin, config, flags, audit`. Each is a package under `src/juggle/modules/` with a **core/ui split**:
  - `core/` — domain models (SQLAlchemy), schemas, and services. **No FastAPI/Starlette imports.** This is enforced by import-linter.
  - `ui/` — the FastAPI router (`ui.router`), thin: parse/validate → call a service → serialise.
- **Module boundaries are enforced, not aspirational.** `make contracts` runs import-linter with two contracts: (1) no `core` imports FastAPI, and (2) modules form a **strict acyclic layering** (high→low: scheduler ▸ admin ▸ analytics ▸ comms ▸ roster ▸ search ▸ reviews ▸ qanda ▸ waitlist ▸ booking ▸ payments ▸ inventory ▸ catalog ▸ org ▸ identity ▸ notifications ▸ flags ▸ config ▸ audit ▸ events). `events` (funnel instrumentation) sits at the very bottom like `audit` — a write-only log every higher module emits to; the funnel read lives in `analytics`. Note `notifications` sits low (a delivery utility like `audit`): callers pass fully-formed content, so booking/payments can call it without a cycle. A module may import only modules **below** it, and cross-module calls go through the lower module's `core.service` (e.g. `catalog` calls `org_service.get_member`), never by reaching into its models from far away. Adding a module = create the package + list its router in `api.py` + place it in the layering.
- **No side-door SQL.** Every mutation — product *and* admin — goes through a module service (PRD §10.4), and auditable actions land in the `audit` module.
- **Deployment config vs runtime config.** `settings.py` (env, `JUGGLE_` prefix) is deployment-only: connection strings, secrets. **Product** config — platform fee %, seat-hold TTL, taxonomy, feature flags — lives in the DB and is edited via the admin panel with versioning + audit (PRD §10.1). Don't hard-code these as constants.
- **Inventory correctness is the product (PRD §12).** Seat holds use row locks / advisory locks with a TTL; booking creation is idempotent; **oversell is impossible by DB constraint** (`bookings_count <= capacity` enforced transactionally), not just by application checks.
- **Child data is sensitive (PRD §11).** Collect the minimum (first name, DOB, medical/emergency contact); no child surname or photos at MVP; never put child PII in analytics events; guardian-only access.
- **Types & style:** mypy strict, no `any`/untyped defs; ruff (`E,F,I,UP,B`); named exports; snake_case Python. Keep dependencies minimal.

## Commands

Run from the repo root (see `make help`). Backend commands run in `apps/api` via `uv`.

| Task | Command |
| --- | --- |
| Install backend deps | `make install` (`uv sync --extra dev`) |
| Start Postgres/PostGIS | `make db` |
| Run API (autoreload) | `make dev` → http://localhost:8000 (`/docs`, `/health`) |
| Full stack in Docker | `make up` |
| Tests | `make test` |
| Lint | `make lint` |
| Type-check | `make typecheck` |
| Module boundary contracts | `make contracts` |
| Migrations | `make migrate` / `make revision m="..."` |
| Maintenance worker | `make worker` (one tick) / `make worker-loop` (every 5 min) |
| Frontend build / tests | `make web-build`, `make web-test` (Vitest units), `make web-e2e` (Playwright, needs stack up) |
| **Everything CI runs** | `make check` |

Run `make check` before considering a change finished.

## Definition of done (per change)

- [ ] `make check` passes (ruff + mypy strict + import-linter + pytest)
- [ ] New/changed behaviour has tests
- [ ] DB invariants (esp. capacity/oversell) enforced at the DB layer, not just in Python
- [ ] Mutations go through a module service and are audited where the PRD requires it
- [ ] No child PII added to logs/analytics events
- [ ] Module boundaries respected (no cross-module `core` imports; new modules added to contracts)

## What NOT to do

- Don't import one module's `core` from another module — use a service interface.
- Don't add FastAPI/Starlette imports inside any `core/` package.
- Don't hard-code runtime/product config (fees, TTLs, taxonomy) — it belongs in DB/admin config.
- Don't enforce capacity only in application code — the DB constraint is the guarantee.
- Don't build out-of-scope surfaces (CCS reporting, term classes, chat/DMs, native apps) — see PRD §17.
- Don't put child surnames/photos in the data model or child PII in analytics.
