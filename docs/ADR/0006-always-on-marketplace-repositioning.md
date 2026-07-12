# ADR 0006 — Always-on marketplace repositioning

- Status: **PROPOSED** (awaiting Turaboy acceptance — this ADR gates Milestones A–D below)
- Date: 2026-07-12
- Invariants touched: INV-1, INV-2, INV-5, INV-6, INV-11, INV-12, INV-13
- Related: PRD §9 (parties), §14 (launch), §15 Risk #3 (seasonality); PRD-EXT-1 E2/G2/§9/§10; ADR 0001–0005
- Supersedes: the phase-gate placement of parties (§9), E2, and G2 as **P2** (they move into the active gate)

## Context

The base PRD positions Juggle as a **school-holiday** activities marketplace: demand arrives in ~4 spikes/year, which the PRD itself names as the #3 risk ("seasonality cashflow… parties (P2) smooth"). Two things that would make the marketplace year-round are currently deferred to P2:

- **E2** (weekend & one-off/drop-in sessions) — mechanically *identical* to holiday sessions (same `session` object, a date outside the holiday calendar): "surface work, not model work."
- **The parties vertical (§9)** and **G2 party invites** — parties smooth cashflow between holiday peaks, and the G2 invite loop is "half the reason to build parties" (EXT-1 §9).

The payments track (F-PAY-0…6) is complete, so the money rails to extend for deposits/balances now exist.

## Decision

1. **Reposition the platform identity to a year-round kids'-activities booking marketplace.** School holidays are the *peak demand moment*, not the scope. All positioning copy (README, homepage, meta) reflects "activities any day," with holidays as a featured peak.

2. **Re-gate** — pull the following from P2 into the **active build gate**, built in sequence **A → B → C → D** (details in `docs/PLANS/always-on-marketplace.md`):
   - **A** — E2 broadened: any-day one-off / drop-in sessions (weekday after-school included). Surfaces + moderation guardrail; no schema change.
   - **B** — Parties: instant-book slots (deposit at booking, balance auto-charged T-7d, guest count adjustable to T-72h).
   - **C** — Parties: request-to-quote (structured brief → quote → accept → deposit via B's rails).
   - **D** — G2 party invites + RSVP (ships *with* parties, not before).

3. **Reaffirm the term-enrolment fence VERBATIM** (EXT-1 §10, and the E2 guardrail): *"No recurring billing or term-enrolment management, ever, under any feature flag."* Recurring-enrolment classes disguised as one-offs are **rejected at moderation** (§10.2). This fence is load-bearing — the repositioning broadens *when* you can book a one-off, never into managing an ongoing relationship. Every milestone plan restates it.

4. **Promote SSR from "built but blocked" to launch-blocking.** A year-round marketplace's demand engine is programmatic SEO (date × region one-off pages, PD-day pages, party pages). SSR stops being a nice-to-have; the Quasar-CLI migration (HANDOFF §9) becomes a gating track, sequenced alongside A–D.

## Consequences

- **Docs to update on acceptance (Step 0 completion):** the CLAUDE.md phase/gate section (see note below), PRD-EXT-1 §9 sequencing (E2/G2/parties move up), and the README positioning line. Held until this ADR is accepted.
- **New money flows (Milestones B/C), all inside the `payments` module, extending F-PAY (INV-2):** partial-capture **deposit** at booking, **scheduled balance auto-charge** at T-7d, and **guest-count adjustment** producing a delta charge/refund until T-72h. These need four decisions resolved first, each its own ADR (draft recommendations in the plan): **D-05** deposit % default/bounds, **D-06** balance-charge failure handling, **D-07** quote expiry + counter-offer policy, **D-08** whether INV-5's refund floor extends to deposits + the weather-clause interplay.
- **Seasonality risk (PRD Risk #3) is directly mitigated** — any-day demand + parties smooth the 4-spike curve.
- **O-1 (platform terms / merchant-of-record) and O-2 (platform insurance) get more pressing** — parties are higher-value transactions with deposits held over time.
- **New party inventory is capacity-managed like sessions (INV-1):** a party slot is capacity-1 inventory; the hold→confirm atomicity + oversell guard apply unchanged.

### Note on the CLAUDE.md gate matrix

The task asks to "update CLAUDE.md §7 gate matrix." That numbered gate matrix lived in the former `CLAUDE2.md`, which PR #1 reduced to a stub (folding invariants/process into `CLAUDE.md` but **not** the phase-gate table). So Step 0 should also **restore a concise "Phase gates" section to `CLAUDE.md`** and record the re-gate there. This is a small correction to PR #1's reconciliation, flagged for the same review.

## Alternatives considered

- **Stay holiday-only, keep parties/E2/G2 at P2.** Rejected: leaves the seasonality cashflow risk unaddressed and cedes the year-round SEO flank (PD-days, weekend one-offs) that EXT-1 identifies as unguarded, high-intent demand.
- **Build parties later as a standalone release (no re-gate now).** Rejected: parties are the cashflow smoother the platform needs *between* peaks, and the G2 invite loop (a top acquisition channel) only exists once parties do — EXT-1 explicitly ships them together.
- **Broaden into term/recurring enrolment (the biggest money pool).** Rejected outright — it's a permanent non-goal (EXT-1 §10); the relationship belongs to the provider. Only the *switch moment* (E4 trial passes, P3) is ever monetised, never the relationship.

## Dependencies

- **PR #1** (adds `docs/juggle-prd-ext-1.md` + the CLAUDE.md/CLAUDE2 reconciliation) should merge before Step 0's doc edits, since this ADR updates PRD-EXT-1 §9 and the CLAUDE.md gate section.
