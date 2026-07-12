# Handoff — 2026-07-12 — Parties frontend (provider mgmt + parent booking) complete

## Scope
Built the **parent-facing party booking UI** and **provider party-management UI** on top of the
B1–B4 parties money backend. This is the "Frontend for parties" gap called out as the natural next
surface in the B4 handoff. On a new branch **`feat/parties-frontend`**, stacked on
`feat/B-parties-decisions` (PR #5) because it consumes that backend.

## What was done

### Backend (small additions to serve the parent page)
- **`GET /api/v1/parties/packages/{id}`** — public single-package detail, enriched with
  `organisation_name`, `venue_name`, `venue_suburb`, and `deposit_pct_effective` (the package's own
  deposit % or the config default via the existing `_deposit_pct`). 404s for missing/archived.
- `schemas.PackageDetailOut` (extends `PackageOut`); `service.effective_deposit_pct` public wrapper.
- `parties.ui.routes` now imports `org` + `catalog` services (both below `parties` in the layering —
  contracts stay KEPT) to resolve the names.
- Two new tests: enriched detail returns names + 30% default; archived package 404s.

### Provider console (`ProviderOrgPage.vue`)
- New **"Party packages"** section: lists packages (name, per-head price, guest band, outdoor,
  status chip); **New package** dialog (venue, name, $/head, min/max, optional deposit %, outdoor —
  disabled until a venue exists); per-package **Add slots** dialog (each slot = one bookable party),
  **Booking link** (copies `/parties/packages/:id` to the clipboard), and **Archive**.

### Parent booking page (`PartyPackagePage.vue`, route `/parties/packages/:id`, public)
- Package header (provider/venue/price/band/outdoor) → **slot picker** → **headcount** (band-checked)
  with a live estimated-total + deposit preview.
- **Reserve → deposit**: `book(slot, headcount)`. Live Stripe uses `StripePaymentPanel` on the
  deposit `client_secret`; dev/FakeGateway uses the `dev-confirm` one-click. Unauthed users are
  bounced to `/login?redirect=…` before reserving.
- **Post-booking management** (ADR-0008/0010 surfaced): change guest count until T-72h (`adjust`),
  and **Cancel booking** with a confirm dialog warning the deposit may be retained.

## Verification
- Backend `make check`: **229 passed** (30 parties tests), mypy strict clean, import-linter **2
  contracts KEPT**.
- Frontend: `vue-tsc --noEmit` clean, `vitest` **20 passed**, `vite build` OK (emits
  `PartyPackagePage` chunk + recompiled `ProviderOrgPage`).

## Known gaps / next
- **No party-booking list surface** for parents: adjust/cancel are reachable only on the page right
  after booking (in-session state). A "my parties" list (like `BookingsPage`) would let a parent
  return later to manage. Deferred — the backend endpoints already exist.
- **Discovery**: parties are found via the provider's shared booking link only; they are not in the
  marketplace search yet (that's the Milestone A / E2 surface work).
- **Live Stripe test-key run** still required for the deposit Payment Element + off-session balance
  path — FakeGateway can't model real `CardError`/3DS.
- `JobSummary` TS type (web) still lacks the B-track scheduler fields (`party_*`) — cosmetic;
  Operations page doesn't read them.
- **Milestone C** (request-to-quote, ADR-0009) and **D** (invites+RSVP, G2/INV-13) remain.

## Git / PR
Committed on **`feat/parties-frontend`** (stacked on PR #5). **Not pushed** — awaiting the go-ahead.
Suggested PR title: "feat(parties): provider management + parent booking frontend". Merge after the
#1→#5 chain lands (it depends on the parties backend).

## Highest-risk thing to pressure-test
The **live deposit Payment Element** end to end against real Stripe test keys: reserve → 3DS bounce
back to `return_url` (`/parties/packages/:id`) → webhook confirms → the page reflects `confirmed`.
The dev path is exercised; the live redirect/return path is not yet run against real Stripe.
