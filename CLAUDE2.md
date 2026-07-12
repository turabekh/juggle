# CLAUDE.md — Juggle (Kids' Holiday-Activities & Party Booking Marketplace)

Instructions for Claude Code working in this repository. Read this file fully at the start of every session. Then read the latest file in `docs/HANDOFF/` before doing anything else.

---

## 1. Project context

Juggle is a two-sided marketplace for Perth (then Australia-wide) families: parents discover and book school-holiday programs and birthday parties with **live availability** and one-cart checkout; providers get free SaaS-lite tools (listings, sessions, rosters, payments) which are the source of that availability data. Revenue: ~10% + GST take rate on marketplace-originated bookings via Stripe Connect.

Authoritative product scope lives in `docs/PRD.md` (v0.1). The build is **gated**: MVP construction only proceeds if the August provider-sprint kill criteria pass (15–20 signed providers, presale evidence). Target: live before the WA spring school holidays (late Sep 2026).

The single most important technical property of this product: **inventory correctness**. A stale seat count or an oversold session destroys the core value proposition. When in doubt, trade features for correctness.

## 2. The Eleven Rules (non-negotiable)

1. **No code comments or docstrings** — except `AI-CONTEXT:` notes where code genuinely cannot speak for itself (LLM-relevant context only). Types and naming do the documenting. `scripts/check_comments.py` enforces this in CI.
2. **Session handoff, always.** Every working session ends with a handoff doc in `docs/HANDOFF/` using the §9 template. Every session starts by reading the latest one.
3. **Never push without asking.** Commit locally freely on feature branches. Pushing, force-pushing, tag-pushing, and merging all require explicit approval in the current session.
4. **Document properly.** Architectural decisions → `docs/ADR/NNNN-title.md` (PROPOSED until Turaboy accepts). Completed features → `docs/FEATURES/F<id>-<slug>.md` referencing PRD section numbers.
5. **Tests with the change.** Unit tests for logic, integration tests for endpoints/DB/payment flows, regression test with every bug fix. Inventory and payment paths require integration tests before merge — no exceptions.
6. **Plan first.** Every non-trivial task starts with a short written plan (steps, files touched, tests, ADR needed?) and explicit agreement before code. Run `plan-critic` on plans for anything touching money, inventory, or child data.
7. **Use MCP servers and subagents** where applicable (matrix in §6).
8. **Docker and docker compose.** If a command isn't run through compose, it didn't run. `infra/docker-compose.dev.yml` is the environment.
9. **Maximum modularity.** Module boundaries in §3 are enforced by import-linter; a negative lint fixture must demonstrably fail.
10. **Quasar, but swappable.** No `quasar` imports outside `apps/web/src/ui/`. Business logic, stores, and API clients live in `apps/web/src/core/` (framework-agnostic TS). Lint rule bans `quasar` in `core/`.
11. **Stack is fixed:** FastAPI + PostgreSQL/PostGIS backend, Quasar (Vue 3, TS) frontend, everything in docker compose.

## 3. Architecture & module boundaries

Monorepo:

```
apps/api/          FastAPI (Python 3.12, uv)
apps/web/          Quasar PWA (SSR for listing pages)
infra/             docker-compose.dev.yml, Dockerfiles, migrations config
docs/              PRD.md, ADR/, FEATURES/, HANDOFF/, PLANS/, RESEARCH.md
scripts/           check_comments.py, dev tooling
```

Backend modules (`apps/api/src/<module>/`), import-linter enforced — a module may import only from modules listed after it:

| Module | Owns | May import |
|---|---|---|
| `shared` | types, errors, clock, ids | — |
| `identity` | guardians, auth (phone-OTP or email), sessions | shared |
| `org` | organisations, members, roles, verification docs (ABN, WWCC, insurance) | shared, identity |
| `catalog` | programs, sessions, venues (PostGIS), pricing | shared, org |
| `inventory` | capacity, seat holds (TTL), availability projection | shared, catalog |
| `booking` | cart, bookings, cancellations, waitlists | shared, identity, catalog, inventory |
| `payments` | Stripe Connect, charges, refunds, payouts, webhooks | shared, booking, org |
| `roster` | per-session rosters, check-in, child medical/emergency data | shared, booking, org |
| `notifications` | email/SMS templates, dispatch, .ics generation | shared, booking |
| `search_geo` | Postgres FTS + PostGIS queries, listing feeds | shared, catalog, inventory |
| `growth` | share links, referrals/credits, invites+RSVP, alert subscriptions, partner attribution (EXT-1; placement ADR at build time) | shared, identity, catalog, inventory (read), booking |
| `admin` | approval queues, moderation, incident register, impersonation session issuance | shared, all read-only + module service surfaces for support mutations |
| `config` | versioned runtime platform settings (fees, TTLs, taxonomy, calendar, templates) | shared |
| `flags` | runtime feature flags (port from Karvon) | shared |
| `audit` | append-only audit events (port from Karvon) | shared |

Cross-module calls go through each module's `service.py` public surface — never reach into another module's models or repos.

## 4. Domain invariants (INV-1…INV-9)

Every plan and every handoff must state which invariants the work touches.

- **INV-1 No oversell.** `confirmed_bookings + active_holds ≤ session.capacity` is enforced transactionally (row lock or advisory lock on session), never in application memory. Seat holds carry a TTL (default 10 min) and expire server-side.
- **INV-2 Money moves only through `payments`.** No other module touches Stripe. All webhook handlers are idempotent (event-id dedupe table).
- **INV-3 Child data minimisation.** Children: first name, DOB, medical/allergy notes, emergency contact only. No child surnames at MVP, no child photos, ever. Child PII never appears in logs, analytics events, error reports, or LLM prompts.
- **INV-4 WWCC gating.** A staff member without a current, verified WA Working with Children Check cannot be assigned to a session roster. Expiry is enforced by query, not by trust.
- **INV-5 Refund floor.** Provider-cancelled session ⇒ automatic 100% refund to every booking, regardless of provider policy settings.
- **INV-6 Price display is GST-inclusive totals** (ACCC component-pricing compliance). The platform fee is calculated fee-exclusive and invoiced +GST.
- **INV-7 Time is UTC in storage, `Australia/Perth` at the edge.** WA has no daylight saving; do not import DST assumptions from eastern-states examples.
- **INV-8 Availability shown = availability true.** Any surface displaying seats remaining reads the inventory projection, never a cached count older than the hold TTL.
- **INV-9 Repo hygiene.** No secrets in the repo; `.env.example` is the contract. No real parent/child data in fixtures — synthetic data only.
- **INV-10 Impersonation is never invisible and never anonymous.** Every impersonation token carries `impersonator_id` alongside `sub`; every action taken under it is audit-logged with the true actor; the impersonated UI always shows the support banner; sensitive actions (credential changes, payment instruments, bank details, payouts, account deletion, child-data export) are hard-blocked during impersonation in both modes. Impersonated actions suppress customer-facing notifications by default.
- **INV-11 Runtime configuration is governed, not free-form.** Every `platform_setting` is typed, bounded (e.g., fee 0–20%), versioned with previous values retained, and audit-logged with the changing admin. Application code reads settings through the `config` module only — no hardcoded values that §10.1 of the PRD says are runtime-configurable, and no other module writing settings.
- **INV-12 Scarcity is never fabricated.** Every urgency signal (spots left, % booked, "filling fast") derives from the live inventory projection — no synthetic countdowns, no fake viewer counts, no thresholds that display sooner than truth. If inventory can't supply the urgency, the urgency doesn't ship.
- **INV-13 Growth surfaces leak no child PII.** Share links, invites, alerts, and digests carry no child names in URLs, params, or analytics; child first name appears in share/invite copy only via per-instance sender opt-in; invitee/guest contact data is scoped to its transactional purpose, with marketing contact requiring separate explicit consent (Spam Act 2003 discipline).

## 5. Commands (all via compose)

```bash
docker compose -f infra/docker-compose.dev.yml up -d        # full stack
docker compose ... exec api uv run pytest                    # backend tests
docker compose ... exec api uv run ruff check .              # lint
docker compose ... exec api alembic upgrade head             # migrations
docker compose ... exec api python scripts/check_comments.py # comment ban
docker compose ... exec web pnpm test                        # frontend tests
docker compose ... exec web pnpm lint                        # incl. quasar-in-core ban
```

**Dev port map:** API `:8000`, Web `:9000`, Postgres host port **`:5439`** (mapped `5439:5432` in compose to avoid collisions with other local stacks). Inside the compose network, services always connect to `db:5432` — the app's `DATABASE_URL` must never reference 5439; only host-side tools (psql, GUI clients, IDE data sources) use `localhost:5439`.

Stripe webhooks locally: `stripe listen --forward-to localhost:8000/webhooks/stripe` (documented in README; never mock webhook signatures in integration tests — use Stripe CLI fixtures).

## 6. Subagent matrix

| Agent | Invoke when |
|---|---|
| `decision-advisor` (Fable) | Any decision with lasting consequences: take-rate mechanics, hold-TTL design, payout timing, schema shape. Protocol: present options + recommendation, record outcome in the ADR. |
| `plan-critic` | Before implementing anything touching INV-1/2/3/4 |
| `code-reviewer` | Every Python PR-sized change |
| `vue-reviewer` | Every Vue/TS change in `apps/web` |
| `standards-checker` | End of each session, against the Eleven Rules |
| `migration-guard` | Every Alembic migration (esp. anything near `inventory`, `payments`) |
| `security-scanner` | Auth flows, webhook handlers, roster/child-data surfaces, impersonation token exchange and blocked-action enforcement, config-write endpoints, compose/secrets changes |
| `test-runner` | After each implementation step |
| `log-detective` | Debugging failed bookings/webhooks |
| `pr-creator` | When Turaboy approves a push |
| `clickup-explainer` | Mapping tickets to PRD feature IDs |
| `bug-discusser` | Triaging user-reported booking/payment issues |

## 7. Phase gate matrix — do not build ahead

Scope tags come from `docs/PRD.md` §6 and `docs/PRD-EXT-1.md` (E/G/B-series). Only **[MVP]** items may be implemented without explicit approval:

| Gate | Contents | Status |
|---|---|---|
| MVP | PRD §7.1–7.5, §8.1–8.4, §10 (search, listing, family profile, cart/checkout, manage bookings; provider onboarding, listings/sessions, roster, payouts; **full admin panel incl. runtime config console §10.1, ops consoles §10.2, impersonation §10.3**) | OPEN once kill criteria pass |
| Pre-launch EXT | G3-lite only (landing-page email + kids'-ages capture) | OPEN |
| P1 | Reviews, waitlists, SMS, promo codes, provider analytics, refund automation, direct-channel fee tier · **EXT-1:** G1 book-together links, G3 alerts, G4 honest scarcity, G5 discover digest, E1 pupil-free days, E3 long weekends | LOCKED until spring MVP ships |
| P2 | Parties vertical, embeddable widget, off-peak deals, chat (if ever) · **EXT-1:** G2 party invites+RSVP (same release as parties), E2 weekend one-offs, G6 referral credits, B1 ELC partner pages, B2 P&C rev-share | LOCKED |
| P3 | CCS-adjacent, KidSport, AI planner, multi-city · **EXT-1:** E4 trial-pass bounties, B3 employer/FIFO benefit | LOCKED |

Anything not in the PRD or PRD-EXT-1: raise it, don't build it. EXT-1 §10 non-goals (no term-enrolment management, no fabricated urgency, no purchased lists) bind at every gate.

## 8. Git discipline

Conventional commits scoped to feature IDs (`feat(F03): session bulk creation`). Branch per feature (`feat/F03-bulk-sessions`). Commit locally at each green step. Rule 3 governs everything remote.

## 9. Session handoff template (`docs/HANDOFF/YYYY-MM-DD-<slug>.md`)

```markdown
# Handoff — <date> — <topic>
## What was done
## Invariants touched (INV-x: how respected/tested)
## Commands run + results
## Decisions made (ADR refs) / decisions deferred
## Known issues & accepted risks (with reasons)
## Next session should
## Highest-risk thing to pressure-test
```

## 10. Trust & safety standing orders

The roster/child-data surface is the most sensitive code in this repository. Changes there always get `security-scanner` + `plan-critic`, always state INV-3/INV-4 in the plan, and never ship the same day they're written — overnight review minimum. A safeguarding failure is existential for this product; velocity never wins that trade.
