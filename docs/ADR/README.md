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
| [0006](0006-always-on-marketplace-repositioning.md) | Always-on marketplace repositioning (E2/parties/G2 into active gate) | ACCEPTED |
| [0007](0007-party-deposit-percentage.md) | Party deposit percentage (default 30%, 10–100%) | ACCEPTED |
| [0008](0008-party-balance-charge-failure.md) | Party balance-charge failure handling | ACCEPTED |
| [0009](0009-party-quote-expiry-and-counters.md) | Party quote expiry + counter-offer policy | ACCEPTED |
| [0010](0010-party-refund-floor-and-weather-clause.md) | Party refund floor vs deposits + weather clause | ACCEPTED |
| [0011](0011-party-planner-vote-to-book.md) | Party Planner — vote-to-book birthday planning (G2 evolved) | ACCEPTED |
