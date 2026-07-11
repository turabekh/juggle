# ADR 0004 — Payout timing: T+2 days after session completion

- Status: **PROPOSED** (awaiting Turaboy acceptance)
- Date: 2026-07-11
- Invariants touched: INV-11 (config), INV-1/INV-5 (refund vs payout ordering)
- Related: PRD §8.4, §10.2 (payout holds), D-04

## Context

D-04: release provider payouts a fixed **N days after each session completes** (per-session,
dispute-buffered), or in a **weekly batch**. The separate-charges model (ADR 0001) lets the
platform choose exactly when each session's `Transfer` is created.

## Decision

Release each session's payout **`session_end + N` days**, with **N = 2** (`payout_delay_days`,
existing config key, default 2, bounded 0–30 — INV-11, no change needed).

- On booking confirmation, `accrue_payout` schedules the session's `Payout` with
  `scheduled_for = session_end_at + payout_delay_days`.
- A clock-controlled release job creates the `Transfer` when `now >= scheduled_for` and the
  payout is not `held`.
- An admin can `hold` an individual session's payout, deferring its transfer indefinitely.

## Consequences

- Matches the PRD dispute buffer with **per-session granularity** and composes cleanly with
  separate transfers + admin holds (ADR 0001) and the reconciliation view (F-PAY-5).
- The 2-day buffer means most refunds (INV-5 provider-cancel; admin refunds) land **before**
  the transfer releases — the common case avoids clawback. Refunds arriving after release
  are handled via transfer reversal (ADR 0001 consequences).
- Release timing is testable by injecting `now` (already the shape of `release_due_payouts`).

## Alternatives considered

- **Weekly batch:** fewer `Transfer` objects and one weekly provider reconciliation, but
  coarser and delays provider cash up to 7 days — weaker for provider NPS (goal G4) and
  no better for disputes. Rejected for MVP; can be layered later as a release-cadence config.
