# CLAUDE.md

Context for Claude Code working in this repository. Read it before making changes, and keep it up to date as the project evolves.

## Project overview

**Juggle** (working title) is a two-sided **booking marketplace for kids' school-holiday activities and birthday parties**, launching in Perth, Australia. It has:

- a **parent-facing marketplace** — search by suburb/date/child-age, live seat availability, one-cart multi-provider checkout, manage bookings;
- **free SaaS-lite tools for providers** — self-serve listings, session/capacity management, live roster, Stripe payouts (this is both the supply hook and the source of live availability);
- a **first-class admin console** — runtime config, provider approval/verification, bookings ops, incident register, and `view-as`/`act-as` impersonation.

The full product spec — requirement IDs, phasing, edge cases, acceptance criteria — is in **`docs/juggle-prd.md`**. It is the source of truth; this file is the engineering orientation on top of it.

> **Status:** Pre-gate per the PRD (build is contingent on the August provider-sprint kill criteria). Progress: scaffold + **M1** (data model), **M2** (identity auth, guardian/child, provider orgs), **M3** (catalog + inventory: sessions + oversell-proof seat holds), **M4** (search: public PostGIS radius + filters), and **M5** (booking checkout: holds→pending→confirmed/cancelled state machine, cart-level idempotency, 10% application fee, age gating, via a `PaymentGateway` interface with a `FakeGateway` — real Stripe drops in behind it). and **M6** (roster: provider attendee lists + CSV, org-member-gated; provider-initiated session cancellation → refund + seat release + reliability ding). Endpoints live on identity, org, catalog, inventory, search, booking, payments, and roster routers. Next: M7 admin/config, then M8 frontend. Confirm milestone scope before implementing.

> **Name:** "Juggle" is a placeholder pending an ASIC/trademark check (PRD D-01). The Python package is `juggle`. If the name changes, update the PRD, this file, the package, and `docker-compose.yml`.

## Tech stack

| Concern | Choice |
| --- | --- |
| Backend | FastAPI (Python 3.12+), managed with `uv` |
| Database | PostgreSQL + **PostGIS** (geo search); SQLAlchemy 2 + Alembic |
| Frontend | Quasar (Vue 3 + TypeScript) — SSR for SEO + installable PWA (not scaffolded yet; see `apps/web/README.md`) |
| Payments | Stripe Connect Express, destination charges (later milestone) |
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

- **Modules (PRD §12):** `identity, org, catalog, inventory, booking, payments, roster, notifications, search, admin, config, flags, audit`. Each is a package under `src/juggle/modules/` with a **core/ui split**:
  - `core/` — domain models (SQLAlchemy), schemas, and services. **No FastAPI/Starlette imports.** This is enforced by import-linter.
  - `ui/` — the FastAPI router (`ui.router`), thin: parse/validate → call a service → serialise.
- **Module boundaries are enforced, not aspirational.** `make contracts` runs import-linter with two contracts: (1) no `core` imports FastAPI, and (2) modules form a **strict acyclic layering** (high→low: admin ▸ notifications ▸ roster ▸ search ▸ booking ▸ payments ▸ inventory ▸ catalog ▸ org ▸ identity ▸ flags ▸ config ▸ audit). A module may import only modules **below** it, and cross-module calls go through the lower module's `core.service` (e.g. `catalog` calls `org_service.get_member`), never by reaching into its models from far away. Adding a module = create the package + list its router in `api.py` + place it in the layering.
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
