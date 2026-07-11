# ADR 0005 — Checkout settlement: firm reservation, card-only MVP, webhook reconciliation

- Status: **PROPOSED** (awaiting Turaboy acceptance)
- Date: 2026-07-11
- Invariants touched: INV-1 (atomic hold→pay→confirm, no oversell/strand), INV-2 (idempotent webhooks), INV-5 (refund reverses payout), INV-11 (config)
- Related: PRD §7.4, §8.4; ADR 0001; plan-critic risk register (findings #1–#8, #11–#14)
- Supersedes the synchronous `confirm()` assumption in `booking.core.service` for the real gateway

## Context

The existing checkout flow assumes payment resolves **synchronously**: `confirm()` calls
`gateway.confirm()` and flips bookings to confirmed in the same request. Real Stripe is
**asynchronous** — the client confirms the PaymentIntent (Payment Element) and the server
learns the outcome via **webhook**, which can arrive late, out of order, duplicated, or
(for async methods like BECS) days later. The plan-critic proved several INV-1 breaks in a
naive port. This ADR fixes the settlement model before any code is written.

## Decision

1. **Firm reservation, not an expiring hold.** At checkout the seat is **committed** (counted
   in `seats_taken`) and stays counted until an **explicit terminal outcome**, never released
   by passive TTL. Terminal outcomes: `payment_intent.canceled`, or an **abandoned-checkout
   sweep** that hard-cancels the PaymentIntent at window end and frees the seat. This removes
   the "webhook after hold expiry" oversell/strand class entirely.

2. **Card-only at MVP** (`payment_method_types=["card"]`). Success/failure lands within the
   checkout window. Async methods (BECS, etc.) are **out of scope** until the firm-reservation
   + reconciliation path is proven.

3. **Webhook is the source of truth for confirmation.** The success handler:
   - reads the **raw request body** and verifies the Stripe signature via
     `stripe.Webhook.construct_event` before parsing (finding #14);
   - runs inside **one transaction per event**: insert into `stripe_event(event_id UNIQUE)`
     **+** all side effects **+** processed-marker commit together; on duplicate key → roll
     back, return 200 (finding #5);
   - takes `SELECT … FOR UPDATE` on the **session row** and the **`Payment` row** (by
     `stripe_payment_intent_id`) to serialise concurrent/duplicate deliveries;
   - if the reservation is still firm → confirm bookings, accrue payout, send invoice;
   - if the seat was somehow lost → **auto-refund the PaymentIntent** and mark the booking
     cancelled/refunded, notify the parent (finding #1). Never confirm a booking whose seat
     cannot be counted.

4. **`payment_failed` is non-terminal** (finding #4): do not release seats on it (a retry can
   still succeed on the same PI). Release only on `payment_intent.canceled` or the sweep.

5. **`gateway.confirm()` is removed from the webhook path** (finding #8): the handler only
   *records* the already-succeeded outcome. The synchronous `confirm()` endpoint remains only
   for `FakeGateway`/tests.

6. **Accrue payout on charged quantity** (`hold.quantity` / the booking's charged units), not a
   live child count (finding #11) — a child deleted between checkout and confirm must not
   under-accrue.

7. **Refunds and payouts are one locked, clawback-aware ledger** (findings #2, #6, #7): every
   refund adjusts the session `Payout` under `SELECT … FOR UPDATE` — decrement if still
   `scheduled`, or issue a **Stripe Transfer Reversal** if already `paid`. `release_due_payouts`
   uses `SELECT … FOR UPDATE SKIP LOCKED`, commits per payout, and passes a Stripe idempotency
   key = `payout.id` so a retry can't double-send (detailed in F-PAY-5).

8. **Separate charges, no destination/application_fee** (finding #9, ADR 0001): the Stripe
   PaymentIntent is a plain charge on the platform account — no `application_fee_amount`, no
   `transfer_data.destination`. `application_fee_cents` is internal accounting/metadata only;
   tests assert the PI params contain neither Stripe field.

## Consequences

- Abandoned checkouts strand a seat until the sweep runs, so the **abandoned-checkout sweep**
  (and a hard PI-cancel at window end) becomes **load-bearing** — it joins the existing
  scheduler tick and must be covered by tests.
- The seat-hold TTL still governs pre-checkout browsing holds; only the checkout step converts
  to a firm reservation. `checkout_window_seconds` config governs the sweep deadline (INV-11).
- More webhook/locking machinery than the synchronous flow, justified by INV-1: this is the
  product's core correctness property.
- Async payment methods are deferred; revisit as a dedicated decision once reconciliation is proven.

## Alternatives considered

- **Keep the expiring hold, tune the window:** cannot survive late/async webhooks; a card
  auth retry alone can exceed the window. Rejected (finding #3).
- **Release seats on `payment_failed`:** strands the subsequent retry-success. Rejected (finding #4).
- **Trust parsed JSON in the webhook body model:** breaks signature verification / invites
  bypass. Rejected (finding #14).
