# Handoff — 2026-07-12 — Parties B3 (T-7d balance auto-charge) complete + reviewed

## Scope
Built **Milestone B3** — the T-7d off-session party **balance** auto-charge + retry + auto-cancel +
payout accrual (ADR-0008/0010). Adversarially reviewed; it found **2 blockers**, both fixed. On
branch `feat/B-parties-decisions` (PR #5), on top of B1+B2.

## What was done
- **`process_party_balances`** scheduler tick: from T-<offset>d, charge each confirmed party's
  balance off-session on the deposit-saved card; retry ≥ interval apart up to max attempts; at
  T-<cutoff>h (or attempts exhausted) **auto-cancel + refund the deposit** (ADR-0010).
- On capture: **standalone provider payout** (net on the full total; `session_id=None` so parties
  don't merge into a session payout), `booking.payout_id` stored for F-PAY-5 clawback.
- Config: `party_balance_offset_days` (7), `party_balance_cutoff_hours` (72),
  `party_balance_retry_interval_hours` (48), `party_balance_max_attempts` (3).
- Gateway `charge_saved_card` (off-session via the deposit PI's customer+payment_method).
  `payments.record_payment` (record a PI-already-created payment) + `accrue_party_payout`.
- Migration `2f69fe381a08` (balance tracking cols + payout FK, clean round-trip).

## Adversarial review — 2 blockers fixed + should-fixes
- **BLOCKER 1** — per-attempt idempotency key would **double-charge** on an ambiguous success (ADR-0008
  wants a stable key). → **stable key** `party-balance-{booking.id}`; retries are ≥48h apart (beyond
  Stripe's 24h idempotency window) so each real retry is fresh, but a same-tick/ambiguous replay dedupes.
- **BLOCKER 2** — an off-session decline **raises `CardError`**, uncaught → the whole scheduler tick
  crashes and permanently wedges. → `StripeGateway.charge_saved_card` catches `CardError` → returns a
  failed status; and `process_party_balances` wraps each booking in a **savepoint** so no one booking
  can abort the tick (tested with a raising gateway).
- **#3** `FOR UPDATE SKIP LOCKED` (no concurrent double-process). **#4** window-vs-cutoff **clamp** (a
  config edit could otherwise auto-cancel every party un-attempted). **#5** ADR-0008 **host
  notifications** (payment-action-needed on decline, cancelled on auto-cancel). **#7** looser refund guard.
- Verdict after fixes: money path sound. `make check` **217 passed**.

## Known gaps / next
- **Provider-side notification** at auto-cancel is not sent (only the host email + an event) — a small
  follow-up; the host (parent) is now properly notified, which was the worst gap.
- Party **Payments carry no per-booking fee/GST breakdown** (0/0; the split lives in the payout net) —
  reporting gap, not a money error (INV-6 satisfied by the single payout accrual). Store if needed for
  reconciliation.
- **B4 — guest-count adjustment (until T-72h):** delta charge (off-session, reuse `charge_saved_card`)
  or partial refund (reuse F-PAY-5 partial-refund + `adjust_payout_for_refund(booking.payout_id)`);
  recompute deposit/balance/total. Also land the **provider/parent-cancel** path that consumes
  `booking.payout_id` for the clawback (the review's forward-looking nit). Adversarial-review the diff.
- **Frontend** for parties (provider package/slot management + parent party booking with the Payment
  Element) is not built — a separate surface.

## Git / PR
PR #5 (`feat/B-parties-decisions`) now = party decisions + B1 supply + B2 deposit + **B3 balance**.
Merge order #1→#2→#3→#4→#5.

## Highest-risk thing to pressure-test
The live off-session balance charge with **real Stripe test keys** — declines, 3DS-required
(`authentication_required`), and the retry cadence. FakeGateway can't model a real `CardError`; the
gateway's decline handling needs a real-key run before relying on it.
