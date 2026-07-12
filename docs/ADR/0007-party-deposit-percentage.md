# ADR 0007 — Party deposit percentage (D-05)

- Status: **ACCEPTED** (Turaboy, 2026-07-12)
- Date: 2026-07-12
- Invariants touched: INV-6 (GST-inclusive display), INV-11 (config-governed)
- Related: ADR-0006 (parties in the active gate), PRD §9; ADR-0008 (balance failure), ADR-0010 (refund floor)

## Context
Instant-book party slots charge a **deposit at booking** and **auto-charge the balance at T-7d**
(PRD §9). We need the default deposit percentage and its bounds. Too low → no-show/cancellation
exposure for the provider; too high → parent friction and larger sums held over time (raising the
merchant-of-record / O-1 stakes).

## Decision
- **Default deposit = 30%** of the GST-inclusive party total.
- **Bounds 10–100%** (100% = "pay in full at booking", no balance step).
- A **runtime config key** `party_deposit_pct` (INV-11), per-venue override allowed later.
- **Two separate charges, not a partial capture** (revised at B2 implementation): the deposit is its
  own PaymentIntent, charged in full at booking, with `setup_future_usage="off_session"` so the card
  is saved; the balance is a **second off-session PaymentIntent** at T-7d (ADR-0008). This is cleaner
  than manual-capture partial settlement (no 7-day uncaptured auth to expire) and reuses the F-PAY
  webhook/settlement rails. Display is GST-inclusive throughout (INV-6): the parent sees the full
  price and "X due today, Y on <date>".

## Consequences
- 30% covers a provider's typical per-party fixed outlay (venue hold, materials) while keeping the
  upfront ask modest. Config-bounded so ops can tune per market without a deploy.
- Larger held sums (higher %) increase platform-terms/insurance exposure (O-1/O-2) — kept visible.

## Alternatives considered
- **Flat dollar deposit.** Rejected: doesn't scale with package size; per-head pricing varies widely.
- **50% default.** Reasonable for high-value parties but higher parent friction at booking; 30% with a
  configurable ceiling gives the same reach without defaulting to it.
