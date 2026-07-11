# Plan — F-PAY-2 checkout settlement (ADR-0002 take-rate + ADR-0005 firm reservation)

Status: in progress · Invariants: INV-1, INV-6, INV-8, INV-11 · ADRs: 0002 (accepted-as-recommended), 0005

## Goal
Make checkout money-correct (GST take-rate) and inventory-safe against async settlement
(firm reservation + abandoned-checkout sweep), without yet moving confirmation onto the
Stripe webhook (that is F-PAY-3). FakeGateway keeps the synchronous confirm path green.

## Increment A — take-rate GST correctness (ADR-0002 rev.2)
Formula per session line (`line = price × qty`, GST-inclusive display):
`fee = round(line·fee_rate)`, `gst = round(fee·gst_rate)`, `net = line − fee − gst`.
Per-session rounding; order aggregates sum the per-session parts (reconciliation closes).

- `config.core.service`: new `gst_rate` key (default 0.10, float, 0–0.20) + `gst_rate()` accessor.
- `payments.core.service`: `fee_gst_cents(fee, gst_rate)`; `take_rate(line, fee_rate, gst_rate)
  -> (fee, gst, net)`; `provider_net_cents(gross, fee_rate, gst_rate)` now subtracts fee **and** gst.
- `payments.core.models.Payment`: add `fee_gst_cents` column (aggregate GST) + migration
  (down_revision = current head `c4e2d1f0a6b7`).
- `create_payment(...)`: accept caller-computed `application_fee_cents` + `fee_gst_cents`
  (booking sums per session so rounding is per-session). Store both on Payment.
- `booking.checkout`: sum per-session fee/gst; pass to create_payment.
- `booking.confirm` accrual: per-session `net = line − fee − gst` via `take_rate`.
- `booking.schemas.OrderOut` + `payments.schemas.PaymentOut`: expose `fee_gst_cents`.
- Tests: update `test_payouts` to GST values (9000→8900, 18000→17800, 7200→7120); new
  `test_take_rate.py` unit (per-session rounding + reconciliation identity
  `Σnet+Σfee+Σgst == order_total`). `test_booking` application_fee_cents==500 unchanged.

## Increment B — firm reservation + abandoned sweep + client_secret (ADR-0005 §1,§2,§8)
- `inventory.core.models.SeatHoldStatus`: add `reserved` (counts against capacity like active,
  but is NOT reclaimed by the TTL sweep).
- `inventory.core.service`: `_reclaim_expired` still only touches `active` (reserved is firm).
  `release_hold` releases `active|reserved`; `force_release` already covers reserved (only
  skips released/expired); new `reserve_hold(hold_id)` helper flips active→reserved under lock.
- `booking.checkout`: convert each hold to `reserved` (firm) instead of extending its TTL.
- `booking.confirm`: move `reserved|active` → `consumed` (seat stays).
- `booking.cancel`: unchanged (release_hold now frees reserved).
- `payments.gateway`: add `cancel_payment_intent(intent_id)` to Protocol/Fake/Stripe.
- `payments.service` + `booking.service`: `sweep_abandoned_checkouts(db, gateway, now)` —
  pending payments older than `checkout_window_seconds` (Payment.created_at): cancel the PI,
  release reserved seats, mark payment failed + bookings cancelled. Idempotent. Returns count.
- `scheduler.run_due_jobs`: call the sweep; add `abandoned_checkouts_swept` to `JobSummary`.
- `create_payment` returns `(Payment, PaymentIntentResult)`; `OrderOut.client_secret` set on a
  fresh checkout so the Payment Element can confirm (None on idempotent replay / order views).
- Tests: `test_checkout_firm_reservation.py` — (1) a checked-out seat survives a
  `reclaim_all_expired` sweep past the TTL (firm), (2) the abandoned sweep after the window
  frees the seat + fails the payment + cancels the PI, (3) confirm before the sweep keeps the
  seat and no sweep touches it, (4) cancel frees the reserved seat.

## Out of scope (later milestones)
Webhook-driven confirm + auto-refund-on-lost-seat (F-PAY-3), Transfer Reversal on refund +
SKIP LOCKED payout release (F-PAY-5), GST tax invoice (F-PAY-6), frontend Payment Element.

## Risks / verification
- Firm reservation makes the abandoned sweep the ONLY reclaimer of a checked-out seat →
  load-bearing, explicitly tested. INV-1 CHECK constraint remains the backstop.
- Money change: net now ~89% (was 90%); test_payouts values updated deliberately per ADR-0002.
- `make check` + targeted pytest after each increment; adversarial self-review of the diff
  against ADR-0005 findings #1–#14 before commit.
