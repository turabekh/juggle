# Handoff — 2026-07-12 — Payments F-PAY-3 (webhook-driven confirmation) complete

## Scope of this session
Third F-PAY milestone in one continuous session (after F-PAY-1 finalise + F-PAY-2). Implemented
**F-PAY-3 — webhook-driven confirmation + auto-refund-on-lost-seat** per ADR-0005 §3–§5. Backend
only; committed on `feat/F-PAY-1-connect-onboarding`. The highest-risk milestone (confirmation
becomes async), so an adversarial review ran on the diff before commit.

## What was done
### Single Stripe webhook sink, correctly placed for the layering
Settlement (confirm bookings, accrue payout, notify, refund) is **booking-level** orchestration,
and `booking` sits ABOVE `payments` in the enforced layering — so payments cannot host it. The
single Stripe webhook endpoint therefore **moved** from `POST /payments/webhook` to
**`POST /api/v1/booking/stripe/webhook`** (verified live; old route gone). `payments` exposes
Stripe-free primitives that `booking` calls downward:
- `verify_event(payload, sig, secret) -> WebhookEvent` — verifies the raw-body HMAC via
  `stripe.Webhook.construct_event`, then reads fields from the **verified JSON** (`json.loads` on
  the same bytes) to dodge `StripeObject`'s attribute quirks. Returns a Stripe-free DTO.
- `record_event` (renamed public; SAVEPOINT dedupe), `apply_account_updated`,
  `get_payment_by_intent(for_update=)`. `mark_succeeded` is now **gateway-free** (records an
  already-succeeded charge — the client confirms the PI; the webhook is truth, ADR-0005 §5).

### booking.handle_stripe_webhook dispatch
- `account.updated` → delegated to `payments_service.apply_account_updated` (Connect flags).
- `payment_intent.succeeded` → `settle_payment_succeeded`: row-locks the payment; if
  `_reservation_is_firm` (every booking pending/confirmed, session not cancelled, hold
  active/reserved/consumed) → `_settle_confirmed` (mark succeeded, consume seats, confirmation
  email, accrue payout — shared with the sync path); else → `_auto_refund_lost_seat` (refund the
  charge, release residual seats, `seat_unavailable_refund` email). Idempotent: unknown PI or
  already succeeded/refunded → no-op; redelivery → `"duplicate"`.
- `payment_intent.canceled` → `settle_payment_canceled`: release seats + fail (terminal).
- `payment_intent.payment_failed` → non-terminal no-op (a retry can still succeed).

### Concurrency + safety
- `cancel_session` / `refund_order` now `get_payment_for_update` (row-lock), serialising with
  webhook settlement.
- **Sync `confirm()` endpoint gated to the fake gateway**: `isinstance(gateway, StripeGateway)`
  → 409. Prevents a guardian confirming + accruing a provider payout with **no charge** when real
  Stripe is live (the adversarial review's should-fix, since `mark_succeeded` is now gateway-free).

## Invariants touched (how respected / tested)
- **INV-1** (no oversell / no strand): `_reservation_is_firm` gates confirm vs auto-refund; the
  adversarial review proved firm-check is necessary+sufficient (matches the hold states that count
  in `seats_taken`). Payment-row locks serialise every settlement path. Tested: succeeded→confirm
  (seat stays), canceled→release (seat freed), succeeded-after-session-cancel→auto-refund.
- **INV-2** (idempotent webhooks; money only via payments): `stripe_event` UNIQUE + status guards
  (no double-confirm/accrue/refund); raw-body signature verified before parsing; all Stripe calls
  stay in `payments`/the gateway. Tested with real HMAC + redelivery.
- **INV-5** (provider-cancel 100% refund): unchanged from before; **payout clawback / Transfer
  Reversal on refund is still F-PAY-5** (a refund after a released Transfer is not yet reversed).

## Commands run + results
- `make check` → ruff + mypy (150 files) + import-linter (2 kept; booking▸payments layering and
  the booking-hosted webhook are legal) + pytest **180 passed**.
- Runtime route check: `/api/v1/booking/stripe/webhook` registered; `/payments/webhook` gone.

## Decisions made / deferred
- Treating **ADR-0005 as accepted** (implementing §3–§5). File still says PROPOSED — Turaboy to
  formally accept.
- **Governance still open**: CLAUDE.md vs CLAUDE2.md; `CLAUDE2.md` + `docs/juggle-prd-ext-1.md`
  remain uncommitted.

## Known issues & accepted risks
- **Payout clawback on refund (INV-5) is NOT done** — F-PAY-4/5. A refund (auto or provider-cancel)
  after a payout has released needs a Stripe **Transfer Reversal**; today refunds don't adjust a
  released `Payout`. Build with F-PAY-5's SKIP-LOCKED + per-payout idempotency-key release.
- **Whole-order auto-refund on a single lost seat** (multi-session cart): correct on money + seats,
  but refunds the entire cart if any one seat is lost. Acceptable for MVP; revisit if partial
  refunds are wanted.
- **Sync `confirm()` remains** for FakeGateway/dev (gated off under live Stripe). It's the path the
  wired Quasar frontend + most tests use; the real Payment Element / client-confirm frontend is a
  later frontend task.
- Per-item sweep commit + idempotent PI-cancel still deferred to F-PAY-5 (ADR-0005 §7).

## Git state
- Branch `feat/F-PAY-1-connect-onboarding`. F-PAY-3 is one commit (`feat(F-PAY-3): ...`). Nothing
  pushed (Rule 3). CLAUDE.md payments status updated (next = F-PAY-4/5/6).
- Branch now carries F-PAY-0 (ADRs), F-PAY-1 (backend+frontend), F-PAY-2, F-PAY-3 + their handoffs.

## Next session should
1. Get Turaboy's ADR acceptance + CLAUDE governance call, then consider **pushing the branch / PR**
   (needs approval, Rule 3) — it's a large, coherent, green payments slice.
2. **F-PAY-4/5 — refund automation + payout ledger**: provider-cancel auto-refund reversing any
   released payout (Transfer Reversal), `release_due_payouts` with `SELECT … FOR UPDATE SKIP
   LOCKED` + per-payout commit + Stripe idempotency key = `payout.id`, and per-item commit for the
   abandoned sweep (idempotent PI-cancel). Then **F-PAY-6** GST tax invoice (needs the string-kind
   config extension for `payment_surcharge_mode`, and `gst_rate` is already in config).
3. **Frontend**: real Stripe Payment Element on checkout using `OrderOut.client_secret` (F-PAY-2
   already returns it), replacing the sync-confirm dev flow for live payments.

## Highest-risk thing to pressure-test
**F-PAY-5 payout clawback**: once payouts can release (T+2), a later refund must claw back money
already transferred to the provider via a Transfer Reversal, under a lock, idempotently. That's the
next place money can leak — a refund that doesn't reverse a released transfer overpays the provider.
