# ADR 0001 — Charge model: separate charges & transfers

- Status: **PROPOSED** (awaiting Turaboy acceptance)
- Date: 2026-07-11
- Deciders: Turaboy (owner), engineering
- Feature chain: F-PAY-1…F-PAY-6
- Invariants touched: INV-1, INV-2, INV-5, INV-6, INV-11
- Related: PRD §8.4, §10.2 (payments ops); open question O-1 (merchant-of-record / platform terms)

## Context

PRD §8.4 asks for two things that are in tension under Stripe Connect:

1. **"Stripe Connect Express, destination charges, application fee."**
2. **"Payout after session completion + N days (dispute buffer)"** plus §10.2 **admin
   payout holds** and a **reconciliation view** (bookings ↔ charges ↔ payouts).

Destination charges (`transfer_data.destination` + `application_fee_amount`) move the
provider's share to their connected account **at capture**. Once moved, the platform
cannot hold an individual session's funds for a 2-day dispute buffer, cannot let an
admin freeze one session's payout, and cannot cleanly reconcile per-session payout
timing — the payout schedule becomes a coarse per-connected-account setting.

## Decision

Use **separate charges and transfers**:

- The platform charges the **full cart total** to the parent's card on the **platform's
  own Stripe balance** (no `application_fee_amount`, no `transfer_data.destination`).
- The platform keeps its 10% + GST simply by **not transferring it**.
- For each booked session, a **Stripe `Transfer`** to the provider's connected account
  is created at **`session_end + payout_delay_days`** (see ADR 0004).
- An admin can **hold** an individual session's payout (`PayoutStatus.held`) so its
  `Transfer` is not created until released.

This matches the existing `Payout` model (`accrue_payout` at confirm, `release_due_payouts`
creating a transfer at T+N) — the skeleton was already built for this shape.

## Consequences

- **Positive:** exact per-session control over payout timing, admin holds, and a
  reconciliation view where `Σ transfers + platform revenue == Σ charges − refunds`.
- **Positive:** the platform's application-fee math is internal, so the 10%+GST
  fee-exclusive rule (ADR 0002, INV-6) is computed in our code, not Stripe's fee field.
- **Negative / dependency:** the platform becomes the **merchant of record** for the
  card charge. This makes **O-1 (platform terms: booking agent vs merchant of record)
  a live legal dependency**, and shifts GST/tax posture. Tracked as an open external
  dependency in the handoff; does not block the build but must be resolved before real
  funds move in production.
- **Negative:** refunds after a `Transfer` has released can drive a **negative connected
  balance** (clawback). Handled in F-PAY-5: prefer refunding before T+N; if a refund
  lands after release, reverse the transfer / debit the connected account per Stripe's
  `reversals` API. (See plan-critic finding on refund-after-transfer.)
- INV-2 preserved: all of this lives in the `payments` module behind the
  `PaymentGateway` Protocol; `FakeGateway` continues to back non-Stripe tests.

## Alternatives considered

- **Destination charge (as literally worded in §8.4):** simplest, provider is merchant
  of record, Stripe handles fee split and tax. Rejected because the N-day dispute buffer,
  per-session admin holds, and reconciliation view degrade to per-account granularity —
  a direct downgrade of PRD §8.4 + §10.2.
- **Destination charge + delayed transfer:** not expressible; destination charges
  transfer at capture and cannot be deferred per-charge.
