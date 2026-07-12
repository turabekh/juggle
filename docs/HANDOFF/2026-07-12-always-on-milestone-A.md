# Handoff — 2026-07-12 — Always-on marketplace: ADR-0006 + Milestone A

## Scope of this session
Started the **always-on marketplace repositioning** (user-directed, plan-first). Wrote and
**accepted ADR-0006**, completed **Step 0** (re-gate docs), and built **Milestone A** (E2: any-day
one-off sessions — surfaces + the term-enrolment fence). On branch `feat/A-anyday-sessions`
(stacked on the governance branch); **not pushed** (Rule 3).

## What was done
### Step 0 — re-gate (docs)
- **ADR-0006** (always-on repositioning) written and marked **ACCEPTED**: parties (§9), E2, G2 pulled
  from P2 into the active gate (A→B→C→D); term-enrolment fence reaffirmed verbatim; SSR promoted to
  launch-blocking. Plan in `docs/PLANS/always-on-marketplace.md`.
- **CLAUDE.md**: year-round positioning; new **Phase gates** section (restores the concept PR #1's
  reconciliation had dropped); term-enrolment fence added to "What NOT to do". **README** positioning
  updated. **PRD-EXT-1 §9** sequencing revised (E2/parties/G2 → active gate).

### Milestone A — E2 any-day sessions (surfaces, not schema)
- **Search facets (Perth-local, INV-7 = fixed UTC+8):** a `when` filter (`weekend`/`weekday`/
  `after_school`) via `AT TIME ZONE` isodow + hour; two feed endpoints **`GET /search/feeds/this-weekend`**
  and **`/after-school`** bounded to the coming week. Reads the live inventory projection (INV-8).
- **Moderation guardrail (the E2 fence):** **`POST /admin/listings/{program_id}/reject`** (admin-gated)
  unpublishes a listing with a reason code; **`recurring_enrolment`** is the fence — recurring/term
  classes disguised as one-offs are pulled from discovery. Audited with the true admin; reason set
  validated. `catalog.admin_unpublish_program` (admin authority, no member check).
- **Frontend:** a "When" chip filter (Weekend / After school / Weekday) on the discover page.

## Invariants touched
- **INV-7** (Perth = fixed UTC+8, no DST): day-of-week/after-school evaluated in Perth local via
  `AT TIME ZONE 'Australia/Perth'`.
- **INV-8** (availability shown = true): feeds/facets read the same live projection as search.
- **INV-12** (no fabricated scarcity): unchanged — no new urgency signals.
- **Term-enrolment fence (ADR-0006/EXT-1 §10):** enforced editorially via the moderation reject reason.

## Commands run + results
- `make check` → **199 passed** (search facet/feed tests + 4 moderation tests). mypy strict + contracts
  (2 kept — admin→catalog is downward). Frontend `vue-tsc` + `vite build` + 20 Vitest green.

## Known issues & accepted risks
- **Dev-DB caution:** earlier this session a live-API smoke script committed rows to the shared dev DB
  and broke global-query tests; fixed by reset + reseed. Also fixed a stale `booking.confirm(gateway=)`
  in `scripts/seed_demo.py` (F-PAY-3 fallout) — see PR #2. **Use the rollback fixture, not committing
  scripts, against the test DB.**
- Milestone A leaves two thin follow-ups: an **admin moderation UI** button (endpoint exists) and
  **curated home-page rows** for the two feed endpoints (endpoints exist; discover `when` filter ships).
- **SEO route stubs** per surface are deferred to the **SSR track** (ADR-0006 promoted SSR to
  launch-blocking) — not built here.

## Git state (branch stack, all unpushed)
- `main` → payments track (F-PAY-0…6 + frontend + tax-invoice UI).
- **Open PRs:** #1 governance/reconciliation + PRD-EXT-1; #2 seed fix.
- `feat/always-on-repositioning` (ADR-0006 + Step 0 + plan) stacked on PR #1's branch.
- `feat/A-anyday-sessions` (Milestone A) stacked on the repositioning branch.
- Recommend merging **PR #2 (seed fix)** and **PR #1 (governance)** first, then PR the repositioning +
  Milestone A.

## Next session should
1. **Merge PRs #1/#2**, then push/PR the repositioning + Milestone A.
2. **Milestone B — parties instant-book (MONEY PATH):** resolve **D-05..D-08** (one ADR each; drafts in
   the plan) first, then build slot inventory (capacity-1, INV-1), deposit-at-booking + T-7d balance
   auto-charge + T-72h guest-count delta (all in `payments`, extending F-PAY). Adversarial review before
   merge; Stripe-CLI-fixture integration tests; clock-controlled balance-charge test.
3. Optional Milestone A polish: admin moderation UI + curated home feed rows.

## Highest-risk thing to pressure-test
Milestone B's **balance auto-charge at T-7d** (off-session PaymentIntent) and the **T-72h adjustment
delta** — a new money path with time-triggered charges. Build it to the F-PAY invariants (INV-2
idempotent webhooks, INV-5/D-08 refund floor incl. deposits) with the same rigor as the payments track.
