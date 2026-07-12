# Handoff — 2026-07-12 — Parties B2 (deposit booking) complete + reviewed

## Scope
Built **Milestone B2** — book a party slot with a **deposit**, webhook-confirmed — the first parties
money step. Adversarially reviewed (found no money-loss bug); the load-bearing gap it flagged is
fixed. On branch `feat/B-parties-decisions` (PR #5), stacked after A/repositioning.

## What was done
- **`book_slot`**: row-locks the `PartySlot` (available→held), creates a `PartyBooking`
  (pending_deposit) + a deposit `payments.Payment` (`purpose=party_deposit`,
  `setup_future_usage=off_session` → card saved for the T-7d balance). Partial UNIQUE
  (`uq_party_slot_active_booking`, one non-cancelled booking per slot) is the INV-1 DB backstop;
  an IntegrityError now surfaces as a clean **409** (review #2).
- **Shared Stripe webhook routes by `Payment.purpose`** (`booking._is_party_payment`): party
  deposits → `parties.settle_deposit_*`, else cart. A deposit can never be mistaken for a cart and
  auto-refunded (INV-2, review-verified). succeeded → confirm + book slot; canceled → release + fail.
- **Abandoned-deposit sweep** (`parties.sweep_abandoned_deposits`, wired into the scheduler tick,
  FOR UPDATE SKIP LOCKED, idempotent): frees a slot stranded `held` when a deposit never confirms
  (Stripe emits no terminal event for an unconfirmed PI) — **review finding #1, the load-bearing gap**.
- `payments.create_payment` gained `purpose` + `setup_future_usage`; gateway
  `create_payment_intent` gained `setup_future_usage`. Config `party_deposit_pct` (30, 10–100).
  Migration `0cde512eacb5` (Payment.purpose backfilled 'cart'; enums; clean round-trip).
- **ADR-0007 reconciled** to the two-separate-charges model (deposit PI now + off-session balance
  PI at T-7d), which the review flagged as diverging from the original "partial capture" wording.

## Verification
- `make check` **212 passed**; mypy strict (157 files); contracts kept (booking ▸ parties ▸ payments).
- Adversarial review (transcript summarised): **no live money-loss bug** — webhook routing sound,
  capacity-1 holds, deposit math within the CHECK, migration round-trips. Findings #1–#3 fixed.

## Known issues & accepted risks (review nits, deferred to B3)
- **#4** `book_slot` holds the slot FOR UPDATE lock across the Stripe PI-create round-trip
  (liveness, not correctness). Consider creating the PI before/outside the lock in B3 if it bites.
- **#5** `settle_deposit_succeeded`'s "booking cancelled → refund deposit" branch is currently
  unreachable; **land it with B3's parent-cancel path** (a cancel that leaves an uncaptured/failed PI
  would make `gateway.refund` error — handle together, per ADR-0010).
- **#6** an orphaned Stripe PI if the `book_slot` txn rolls back after PI-create (harmless: never
  charged, auto-expires) — the cart flow sidesteps this via idempotency-key reuse; adopt if needed.
- Party payout accrual + parent confirmation email are **not** at deposit time (intended — they
  belong at balance/completion, B3/B4).

## Next — B3 (T-7d balance) + B4 (T-72h adjustment), MONEY PATH
- **B3:** at T-7d, a scheduler job charges the **balance off-session** (second PaymentIntent on the
  saved card; idempotency key `booking.id+"balance"`), retry [7,5,3]d with host emails, at T-72h
  notify provider + auto-cancel + refund deposit (ADR-0008/0010). Parent-cancel path (land review #5).
  Accrue the provider payout (take-rate per ADR-0002) at balance capture / completion.
- **B4:** guest-count adjustment until T-72h → delta charge/refund (reuse F-PAY-5 partial-refund +
  clawback). Recompute deposit/balance.
- Adversarial-review the B3/B4 diff before merge; clock-controlled balance-charge integration test.

## Git / PR
- PR #5 (`feat/B-parties-decisions`) now = party decisions (0007–0010) + B1 supply + **B2 deposit**.
  Stacked on #4. Merge order #1→#2→#3→#4→#5.

## Highest-risk thing to pressure-test
B3's **off-session balance charge** — a time-triggered charge on a saved card with retries and an
auto-cancel-at-T-72h. Same rigor as F-PAY (INV-2 idempotent, INV-5/ADR-0010 refund floor).
