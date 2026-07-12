# Handoff — 2026-07-12 — Payments F-PAY-4/5 (refund automation + payout clawback) complete

## Scope of this session
Fourth/fifth F-PAY milestone in one continuous session (after F-PAY-1/2/3). Implemented
**payout clawback on refund + payout-release hardening** (ADR-0005 §7, INV-5). Backend only;
committed on `feat/F-PAY-1-connect-onboarding`. Money-critical, so an adversarial review ran on
the first cut — it found a **BLOCKER**, which this handoff's final code fixes.

## What was done
### The problem
Before this, a refund (provider session-cancel or admin order-refund) returned money to the family
but the provider's accrued **payout still stood** — the platform silently ate the loss (INV-5 gap).

### First cut + the review
The first implementation clawed back by **recomputing** the net at refund time and **guessing** the
session's payout. The adversarial reviewer proved two money bugs:
- **BLOCKER**: a session can hold >1 qualifying payout (a released `paid` one + a fresh `scheduled`
  one after a later booking). A per-session guess (`ORDER BY created_at`) reversed the WRONG,
  already-paid transfer and left the refunded order's scheduled payout to be paid later.
- **config drift** (should-fix): recomputing net under a fee/gst rate changed since confirm
  under-clawed and stranded money with the provider.
- **over-refund** (should-fix): `cancel_session` refunded the WHOLE multi-session order and clawed
  back all its payouts, stranding sibling sessions that still stand.

### The fix (final code)
Persist the ledger link instead of recomputing/guessing:
- **`booking.accrued_net_cents` + `booking.payout_id`** recorded at confirm (`_settle_confirmed`),
  and **`payment.refunded_cents`** for partial refunds (migration `f7c5d4e3a8b9`, round-trips clean).
- `adjust_payout_for_refund(payout_id, net_cents, …)` targets the **exact** payout (row-locked):
  decrement if `scheduled`/`held`, Stripe **Transfer Reversal** if `paid`; `min()`-guarded; zeroes
  → `reversed`. `_clawback_booking` reverses `booking.accrued_net_cents` from `booking.payout_id`
  with idempotency key `rev-{booking.id}`.
- `payments.refund(…, amount_cents=None)` supports **partial** refunds (tracks `refunded_cents`,
  sets `partially_refunded` until full). `cancel_session` now refunds only the cancelled session's
  line total and claws back only its bookings; `refund_order` stays a full-order admin refund.
- `release_due_payouts`: `SELECT … FOR UPDATE SKIP LOCKED`, idempotency key `= payout.id`, skips
  `amount<=0` (fully clawed-back) payouts. Gateway gains `reverse_transfer` + an idempotency key
  on `transfer`.

## Invariants touched (how respected / tested)
- **INV-5** (provider-cancel ⇒ family refunded AND provider not kept whole): clawback reverses the
  provider payout. Tested: refund-before-release decrements the scheduled payout to 0/`reversed`;
  refund-after-release issues a Transfer Reversal (payout `reversed`, a later run doesn't re-pay);
  session-cancel claws back.
- **Money conservation / BLOCKER**: `test_refund_targets_the_bookings_own_payout_not_a_sibling`
  (2 orders on one session, first released → refunding the second reverses P2, leaves P1 paid),
  and `test_clawback_is_exact_after_a_fee_config_change` (raise fee to 20% post-confirm → still
  claws back the stored 8900, not the recomputed 7800).
- **INV-2**: Transfer Reversal idempotency key `rev-{booking.id}` (unique per booking, stable on
  retry); release key `payout.id`.

## Commands run + results
- `alembic upgrade head` → `f7c5d4e3a8b9`; downgrade→upgrade round-trips clean; single head.
- `make check` → ruff + mypy (150 files) + import-linter (2 kept) + pytest **185 passed**.

## Decisions made / deferred
- Treating ADR-0005 §7 / ADR-0001/0004 as accepted (implementing). Files still PROPOSED — Turaboy
  to accept/amend.
- Governance still open: CLAUDE.md vs CLAUDE2.md; `CLAUDE2.md` + `docs/juggle-prd-ext-1.md` uncommitted.

## Known issues & accepted risks
- **Release crash-window (should-fix 3, DEFERRED)**: `release_due_payouts` flushes once and relies
  on the caller's single commit. If the Stripe transfer succeeds but the txn then rolls back AND a
  clawback reduces the still-`scheduled` payout before a retry, the retry replays the stale (larger)
  amount via idempotency key `payout.id`. Real fix = **per-payout commit** (mark paid + commit
  atomically with each transfer), which the shared-transaction test harness (`conftest.db` rolls
  back) blocks. Narrow (needs a sub-second crash + intervening clawback). Address when the worker
  gets a real per-item commit path outside the test harness.
- **Auto-refund-on-lost-seat still refunds the whole payment** (F-PAY-3 path) even for a
  multi-session order — the per-session partial logic added here is in `cancel_session`, not that
  path (lost seats are rare and never accrued a payout). Consider unifying if multi-session lost
  seats become real.
- Config-driven `platform_fee_rate`/`gst_rate` changes now only affect FUTURE confirmations, not
  past clawbacks (correct) — but mixing rates across a session's payout is possible; reconciliation
  is still exact because each booking carries its own accrued net.

## Git state
- Branch `feat/F-PAY-1-connect-onboarding`. F-PAY-5 is one commit (`feat(F-PAY-5): …`). Nothing
  pushed (Rule 3). CLAUDE.md payments status updated (next = F-PAY-6). This branch now carries
  F-PAY-0…5 + handoffs — a large, green payments slice ready for review/PR.

## Next session should
1. Get Turaboy's ADR acceptance + CLAUDE governance call, then **push the branch / open a PR**
   (needs approval, Rule 3).
2. **F-PAY-6 — GST tax invoice**: a provider-facing tax invoice per order/session itemising the
   platform→provider taxable supply (commission `application_fee_cents` + GST `fee_gst_cents`,
   already stored on Payment). Likely a notifications template + a read endpoint; no new money math.
3. Optionally implement the deferred **per-payout commit** for release, and unify the lost-seat
   refund with per-session partials.
4. **Frontend**: real Stripe Payment Element using `OrderOut.client_secret`.

## Highest-risk thing to pressure-test
The **release crash-window** (deferred above) is now the sharpest remaining money edge: a transfer
that sends but doesn't commit, then gets re-sent for a stale amount. Until per-payout commit lands,
treat `release_due_payouts` as at-least-once with an amount that must not change between attempts —
i.e. don't let a clawback race an in-flight release in production (the SKIP LOCKED helps, but the
post-crash reload is the gap).
