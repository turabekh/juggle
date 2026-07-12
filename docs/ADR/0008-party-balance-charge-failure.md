# ADR 0008 — Party balance-charge failure handling (D-06)

- Status: **ACCEPTED** (Turaboy, 2026-07-12)
- Date: 2026-07-12
- Invariants touched: INV-1 (slot inventory), INV-2 (idempotent charges/webhooks), INV-5/ADR-0010 (refund floor)
- Related: ADR-0006, PRD §9; ADR-0007 (deposit), ADR-0010 (refund floor)

## Context
The party **balance auto-charges at T-7d** as an **off-session** PaymentIntent (the card the parent
used for the deposit, saved for future use). Off-session charges fail routinely (expired card,
insufficient funds, issuer decline). We need a deterministic failure path that protects the provider's
slot without silently cancelling a real booking.

## Decision
A scheduler-driven, **idempotent** balance-charge job (like the F-PAY abandoned-checkout sweep):

1. **At T-7d:** attempt the balance charge (off-session, idempotency key = `booking.id`+`"balance"`).
2. **On failure:** email the host "payment needs attention" with a self-service link to update the
   card + retry. **Retry schedule: T-7d, T-5d, T-3d** (3 attempts).
3. **At T-72h** (the guest-count adjustment cutoff), if still unpaid: **notify the provider**, then
   **auto-cancel the booking**, release the slot (INV-1), and refund the **deposit per ADR-0010**
   (deposit is refunded to the parent — a failed balance is not the provider cancelling, but the
   platform will not forfeit the parent's deposit for a payment-method failure; ops may override with
   an audited reason for genuine no-shows).
4. All state transitions are audited; the job is safe to re-run (idempotent charge + status guards).

Config keys (INV-11): `party_balance_retry_days` (default `[7,5,3]`), `party_balance_cutoff_hours`
(default 72, aligned to the adjustment cutoff).

## Consequences
- The provider's slot isn't held indefinitely by an unpayable booking; the parent gets 3 chances +
  clear comms before any cancellation.
- Deposit-refund-on-payment-failure is the parent-friendly default; flag for review if providers push
  back (a partial deposit forfeit for late payment-method failure is a possible future config, not now).

## Alternatives considered
- **Cancel on first failure.** Rejected: off-session declines are often transient (issuer 2FA, temp
  limit); one failure ≠ intent to abandon.
- **Never auto-cancel (hold forever).** Rejected: strands the provider's slot (INV-1 value) and the
  T-72h adjustment cutoff needs a settled headcount.
- **Forfeit the deposit on failure.** Rejected as the default (parent-hostile for a card glitch); left
  as a possible audited ops override.
