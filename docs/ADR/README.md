# Architecture Decision Records

One decision per file, `NNNN-title.md`. Status is **PROPOSED** until Turaboy accepts, then
**ACCEPTED** (or **SUPERSEDED** by a later ADR). Every decision with lasting consequences
(take-rate, hold-TTL, payout timing, schema shape) is recorded here per house rules.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-charge-model-separate-charges-and-transfers.md) | Charge model: separate charges & transfers | PROPOSED |
| [0002](0002-take-rate-fee-exclusive-plus-gst-per-session-rounding.md) | Take-rate: 10% fee-exclusive + GST, per-session rounding | PROPOSED |
| [0003](0003-card-surcharge-absorbed.md) | Card surcharge: absorbed (no pass-through) at MVP | PROPOSED |
| [0004](0004-payout-timing-t-plus-2.md) | Payout timing: T+2 days after session completion | PROPOSED |
| [0005](0005-checkout-settlement-firm-reservation-and-webhook-reconciliation.md) | Checkout settlement: firm reservation, card-only MVP, webhook reconciliation | PROPOSED |
