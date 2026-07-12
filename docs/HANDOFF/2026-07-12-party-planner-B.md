# Handoff — 2026-07-12 — Party Planner Milestone B (surfaces)

## Scope
Milestone B of the Party Planner (ADR-0011) — the **frontend surfaces** on the A backend: the host
build/manage/confirm flow and the public invitee RSVP + vote page. On `feat/party-planner-B`
(stacked on `feat/party-planner-A`), **not pushed**.

## What was built

### Host (authenticated)
- **`PartyPlansPage`** (`/parties/plans`): list of the host's plans + **New plan** (creates a draft,
  routes to manage). Entry points: a "Start a vote" button on `PartiesPage` and "Party plans" in the
  account menu.
- **`PartyPlanManagePage`** (`/parties/plans/:id`): status-driven —
  - **draft**: add package options (package + slot picker), one custom option, ⭐ favourite (drives
    tie-break via ranking), deadline (with the backend's deadline warnings surfaced) → **open** (gated
    on ≥2 options incl a package + a deadline) → share link.
  - **open**: copy share link, **extend 48h**, live tally bars, **approval queue** (approve/block),
    guest list.
  - **resolved**: winner (or "it's a tie — you choose"), **confirm/override** with a headcount
    prefilled from Σ yes-RSVPs → **deposit hand-off** (dev-confirm, or `StripePaymentPanel` in live).
  - **booked**: success.

### Invitee (public, tokenized, no account)
- **`PartyPlanRsvpPage`** (`/parties/plan/:token`): RSVP form (name/email/kid-count/nickname/avatar/
  marketing opt-in + an off-screen **honeypot**) → **pending-approval** banner → **vote cards** with a
  live tally (**10s poll**, no websockets) → **reveal** (winner or tie) + a **"plan your own party"**
  CTA. The invitee's own choice is remembered **client-side only** (localStorage) — the server never
  returns which option (anonymity). The **board is avatars-only** (no child data, no names). The page
  is **`noindex`** (INV-13, via a new `useHead` option).

### Backend glue (small)
- `confirm` now returns the deposit **PaymentIntent** so the response carries `deposit_client_secret`
  + `deposit_payment_id` + `deposit_cents` (host can settle the deposit right after confirming).
- `useHead` gained a `noindex` option; the seed enables the `party_planner` flag for local dev/e2e
  (prod stays OFF until real email, per ADR).

## Privacy self-review (INV-3/12/13)
No child data on any planner surface; the who's-in board renders avatars only; votes are anonymous
(own vote is client-only localStorage, never from the API); honeypot hidden; share link is the opaque
token; token page is `noindex`. Confirmed against the built pages.

## Verification
- Frontend: `vue-tsc` clean, `vite build` OK (emits the 3 planner pages), `vitest` **20 passed**.
- e2e: `party-planner.spec.ts` compiles (`playwright test --list`); it drives invitee RSVP → host
  approve → vote → tally through the UI. **Resolution/confirm is clock-driven** (scheduler tick) and
  is not e2e-drivable without an admin/clock hook — that leg is covered by the **22 backend
  integration tests** (clock-controlled `resolve_due_plans`).
- Backend `make check` **252 passed**, mypy strict, import-linter **2 contracts KEPT**.

## Try it in dev
The `party_planner` flag is now enabled on the local dev DB (and in `make seed`). Log in, open
**Parties → "Start a vote"** (or the account menu → **Party plans**), build a plan from the seeded
demo party packages, open it, and hit the share link in another browser to RSVP + vote. Deposit uses
the one-click dev-confirm (no Stripe keys needed).

## Known gaps / next
- **Resolution in e2e:** needs the deadline to pass + a scheduler tick; not automated here (backend
  tests cover it). A future admin "run scheduler now (with clock)" hook would let the full e2e run.
- **Live deposit path** (Payment Element in the manage page) is wired but unverified without Stripe
  test keys — same status as the rest of the payments UI.
- **Milestone C (gamified):** theme skins, countdown polish, animated tally, confetti, readiness
  meter, emoji reactions — the current surfaces are functional, not yet gamified.
- **Milestone D (lifecycle + notifications + purge):** invite/reveal/override/detail-request emails,
  the low-RSVP + re-vote nudges (markers already on the model), and the PII purge job (must also
  purge the child roster on `PartyBooking`; account-less child-data collection path still to spec).
