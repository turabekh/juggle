# ADR 0010 — Party refund floor vs deposits + weather clause (D-08)

- Status: **ACCEPTED** (Turaboy, 2026-07-12)
- Date: 2026-07-12
- Invariants touched: INV-5 (refund floor), INV-6 (GST-inclusive), INV-2 (money via payments)
- Related: ADR-0006, PRD §9, §11 (refund floor); ADR-0007 (deposit), ADR-0008 (balance failure), ADR-0004 (payout timing)

## Context
INV-5 mandates: **a provider-cancelled session ⇒ 100% refund, overriding provider policy.** Parties add
two wrinkles the base invariant didn't face: a **deposit** held from booking, and a **weather clause**
for outdoor venues. We must decide whether INV-5 extends to the deposit, and what the weather clause may
and may not do.

## Decision
1. **INV-5 extends to parties in full: a provider-cancelled party ⇒ 100% refund of everything paid,
   deposit included, always** — and any payout already released is clawed back (F-PAY-5 rails, Transfer
   Reversal). Provider party-policy settings can never reduce this floor.
2. **The weather clause may only RESCHEDULE, never forfeit.** For an outdoor party hit by weather, the
   provider may offer a rescheduled slot; if the parent declines (or no slot works), it falls back to
   the **INV-5 100% refund**. A weather cancellation is **never** a platform-side forfeiture of the
   parent's money. The clause is a reschedule *option*, not a refund exception.
3. **Parent-initiated cancellation** follows the provider's stated party policy **down to a floor**: the
   platform guarantees at least the **deposit-forfeit-only** outcome is the provider's *maximum* retained
   amount unless within a config window — i.e. providers set their own parent-cancel terms, but the
   platform never lets a provider retain **more than the deposit** for a parent cancel outside the
   adjustment window, and refunds the balance if already charged. (Deposit is the provider's protection;
   the balance is not a penalty pool.)
4. Deposits and balances both move only through `payments` (INV-2); all refunds/clawbacks reuse F-PAY-5.

## Consequences
- Parents are never out-of-pocket for a provider/weather cancellation — the trust property the whole
  marketplace rests on (PRD Risk #4 safeguarding-adjacent trust).
- Providers keep at most the deposit on a parent cancel (their fixed-cost protection), never the balance
  as a penalty. Config key `party_parent_cancel_window_hours` governs the "full refund incl. deposit"
  courtesy window (default 0 = provider policy applies immediately; ops can widen).

## Alternatives considered
- **Deposit non-refundable even on provider cancel.** Rejected outright — violates INV-5 and the core
  trust promise; a provider cancelling and keeping the deposit is exactly what INV-5 forbids.
- **Weather clause allows forfeiture.** Rejected: weather is not the parent's fault; reschedule-or-refund
  is the only fair outcome and keeps the "no fabricated penalties" spirit.
