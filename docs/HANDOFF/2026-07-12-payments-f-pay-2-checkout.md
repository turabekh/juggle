# Handoff — 2026-07-12 — Payments F-PAY-2 (checkout settlement) complete

## Scope of this session
Continued the Payments track. After finalising F-PAY-1 (separate handoff), implemented
**F-PAY-2 — checkout settlement** end to end: the GST-correct take-rate (ADR-0002) and the
firm-reservation + abandoned-sweep inventory model (ADR-0005). Backend only; committed on
`feat/F-PAY-1-connect-onboarding`. The user directed "use your best judgement and continue/
complete", so the recommended ADR options are treated as accepted (see Decisions).

## What was done
### Take-rate GST correctness (ADR-0002 rev.2 — fixes INV-6)
- New `gst_rate` config key (default 0.10, float, 0–0.20) + `config_service.gst_rate()`.
- `payments.service`: `fee_gst_cents(fee, gst)`, `take_rate(line, fee, gst) -> (fee, gst, net)`;
  `provider_net_cents(gross, fee, gst)` now subtracts fee **and** GST (provider nets ~89%).
- `Payment.fee_gst_cents` column (migration `d5a3b2c1e6f8`). `create_payment` takes caller-summed
  fee + GST so rounding stays **per session**; `booking.checkout` sums per-session lines.
- Payout accrual uses per-session `net = line − fee − gst` on the **charged quantity**
  (`_charged_quantity` = immutable hold qty, not a live child count — ADR-0005 §6).
- `OrderOut` / `PaymentOut` expose `fee_gst_cents`.

### Firm reservation + abandoned sweep (ADR-0005 §1,§2,§8 — protects INV-1)
- New `SeatHoldStatus.reserved` (migration `e6b4c3d2f7a9`, `ALTER TYPE ADD VALUE`): a checked-out
  seat counts against capacity but is **not** reclaimed by the TTL sweep (`_reclaim_expired` still
  only touches `active`). Seats are **reserved before the Stripe call** so a reclaim mid-payment
  can't strand a paid seat; if the seat was lost meanwhile, checkout raises `HoldExpired`.
- `booking.confirm`: `active|reserved → consumed`. `booking.cancel`: `release_hold` frees reserved.
- `sweep_abandoned_checkouts(db, gateway, now)` — pending payments older than `checkout_window`
  (`Payment.created_at`): cancel the PI (`gateway.cancel_payment_intent`), free reserved seats,
  fail the order. `FOR UPDATE SKIP LOCKED`, idempotent. Wired into `scheduler.run_due_jobs`
  **before** waitlist processing (freed seats offer same tick); `JobSummary.abandoned_checkouts_swept`.
- `create_payment` returns `(Payment, PaymentIntentResult)`; `OrderOut.client_secret` set on a
  fresh checkout for the Payment Element (None on idempotent replay / order views).

### Concurrency hardening (from the adversarial review — the load-bearing part)
An adversarial "plan-critic" pass on the diff found one root defect: seat/hold decisions made
**outside the session row lock**, which the new sweep + `reserved` status made raceable. Fixed:
- `release_hold` / `force_release` / `reserve_hold` now **lock the session first, then re-read the
  hold under the lock** before deciding — two concurrent releasers (e.g. provider-cancel racing the
  sweep) can no longer both decrement `seats_taken` for the same hold.
- `booking.confirm` / `booking.cancel` **row-lock the Payment** (`get_payment_for_update`) so a
  concurrent sweep can't flip it to `failed` on a stale `pending` read (ADR-0005 §3).
- `reserved` holds now count toward the anti-hoarding cap.

## Invariants touched (how respected / tested)
- **INV-1** (no oversell / no strand): firm reservation + lock-first-then-recheck seat mutations +
  row-locked payment transitions. Tests: reserved seat survives a TTL sweep; abandoned sweep frees
  + fails + is idempotent; confirmed order never swept; cancel frees reserved; **double
  force_release doesn't underflow**; reserve refuses a reclaimed seat. CHECK `ck_session_no_oversell`
  remains the backstop.
- **INV-6** (GST-inclusive display, fee ex-GST +GST): per-session `take_rate`; DB-level
  reconciliation test `application_fee + fee_gst + Σnet == amount` on a multi-session cart.
- **INV-11**: `gst_rate` is a bounded/audited config key.

## Commands run + results
- `alembic upgrade head` → applied `d5a3b2c1e6f8`, `e6b4c3d2f7a9`; downgrade→upgrade round-trips
  clean; `alembic heads` single (`e6b4c3d2f7a9`).
- `make check` → ruff + mypy (150 files) + import-linter (2 kept; scheduler▸booking▸payments
  layering intact) + pytest **174 passed**.

## Decisions made / deferred
- Treating **ADRs 0002 & 0005 as accepted** (recommended options) to implement F-PAY-2; their
  files still say **PROPOSED**. Turaboy: formally accept or amend (esp. the GST net formula
  `net = line − fee − gst`, which changed payout values 9000→8900 / 7200→7120 in tests).
- **Governance still open**: CLAUDE.md vs CLAUDE2.md; `CLAUDE2.md` + `docs/juggle-prd-ext-1.md`
  remain uncommitted.

## Known issues & accepted risks
- **Sweep is not per-payment committed** (ADR-0005 §7 scopes per-item commit to F-PAY-5). A
  mid-batch failure rolls back the DB but not any Stripe PI cancels already sent; a re-run would
  try to cancel an already-canceled PI (Stripe errors). Low risk with FakeGateway/card-only;
  **harden in F-PAY-5** with per-item commit + idempotent/ignore-already-canceled.
- The synchronous `confirm()` endpoint is the shipped confirmation path this milestone but is
  **FakeGateway/test-only by design**; real confirmation is webhook-driven in **F-PAY-3** (which
  must take `FOR UPDATE` on the session + Payment rows, per ADR-0005 §3, and auto-refund on lost seat).
- DB enum value `reserved` is appended after `expired`, so DB enum order ≠ Python enum order —
  harmless (no `ORDER BY status`), noted if anyone adds ordered status comparisons.

## Git state
- Branch `feat/F-PAY-1-connect-onboarding`. F-PAY-2 is one commit (`feat(F-PAY-2): ...`).
  Nothing pushed (Rule 3). CLAUDE.md payments status updated (next = F-PAY-3).

## Next session should
1. Get Turaboy's ADR-0002/0005 acceptance + the CLAUDE governance call.
2. **F-PAY-3 — webhook-driven confirmation** to ADR-0005 §3: `payment_intent.succeeded` handler
   locks the session + Payment rows, confirms + accrues + invoices if the reservation is still
   firm, else **auto-refunds the lost seat**; `payment_intent.canceled` releases; `payment_failed`
   is non-terminal. Then retire the synchronous confirm path for the real gateway. Run the
   race-ordering integration tests first. Re-run the adversarial review on that diff.

## Highest-risk thing to pressure-test
The webhook-vs-seat reconciliation in F-PAY-3 — now that F-PAY-2 has committed the firm-reservation
model, the remaining oversell/strand risk lives entirely in making confirmation webhook-driven with
proper row locks + auto-refund-on-lost-seat. Build it with the race tests before anything downstream.
