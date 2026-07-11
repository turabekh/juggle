# ADR 0002 — Take-rate mechanics: 10% fee-exclusive + GST, per-session rounding

- Status: **PROPOSED** (awaiting Turaboy acceptance)
- Date: 2026-07-11 (rev. 2 — corrected net formula after plan-critic finding #10)
- Invariants touched: INV-6 (GST-inclusive display, fee fee-exclusive +GST), INV-11 (config)
- Related: PRD §7.4, §8.4, D-02; ACCC component-pricing (single total shown)

## Context

INV-6 mandates the platform fee be **calculated fee-exclusive and invoiced +GST**, while
the price the parent sees stays **GST-inclusive**. Today's code (`application_fee_cents =
round(amount_cents * fee_rate)`) takes a **fee-inclusive slice of gross with no GST line**
— this contradicts INV-6 and is replaced by this ADR.

The remaining choices are (a) the exact formula, (b) the rounding base, and (c) where the
rate and GST live. The first draft of this ADR wrote `net = line − fee`, which the
plan-critic (finding #10) flagged as contradicting "platform keeps 10% **+ GST**": that
formula treats the fee as GST-*inclusive*. PRD §8.4 ("10% + GST") and INV-6 ("fee-exclusive
and invoiced +GST") both mean the provider is charged a 10% commission **plus** GST on that
commission — corrected below.

## Decision

**Per-session rounding**, so each session's payout is exact and the parts sum to the whole
with no allocation drift (payout accrual is per-session, ADR 0001/0004). `net` is the
**derived remainder** per session so reconciliation always closes to the charge.

For each session line (`price_cents × quantity = line_cents`, GST-inclusive display price):

```
fee_cents = round(line_cents * platform_fee_rate)     # 10% commission, ex-GST — platform revenue
gst_cents = round(fee_cents * gst_rate)               # GST on the commission — platform remits to ATO
net_cents = line_cents - fee_cents - gst_cents        # provider payout for the line (derived)
```

Order-level:

```
order_total_cents      = Σ line_cents                 # charged to the parent, GST-inclusive display
platform_take_cents    = Σ fee_cents + Σ gst_cents    # retained (not transferred): fee = revenue, gst = ATO liability
Σ transfers            = Σ net_cents                  # paid out to providers
```

**Reconciliation identity (asserted in F-PAY-5 tests):**
`Σ net_cents + Σ fee_cents + Σ gst_cents == order_total_cents` for any multi-session cart.

The **tax invoice** (F-PAY-6) itemises the platform→provider taxable supply: commission
`fee_cents` + GST `gst_cents`. The **parent** is shown only the GST-inclusive session
price(s) they paid (INV-6 display rule); the commission/GST split is a provider-facing line.

- `platform_fee_rate` — existing config key (default 0.10, bounded 0–0.20).
- **`gst_rate`** — NEW config key (default 0.10, bounded 0–0.20) (INV-11).

`round()` is banker's rounding; cents are integers and each of `fee`/`gst` is rounded once
per session, with `net` derived by subtraction, so per-session parts sum to the order total
exactly (no allocation remainder).

## Consequences

- Provider nets ~89% of the GST-inclusive session price (100% − 10% fee − 1% GST-on-fee).
- Replaces the current fee-inclusive math; `payments.service.application_fee_cents` keeps its
  signature; a new `fee_gst_cents` helper is added and `provider_net_cents` subtracts both
  fee and GST.
- The GST line does **not** inflate the parent's total; it is deducted from the provider's
  payout and remitted by the platform (INV-6).
- If the provider is GST-registered they reclaim `gst_cents` as an input tax credit — outside
  our system; we only record and remit.

## Alternatives considered

- **Platform absorbs the commission-GST (`net = line − fee`):** provider nets 90%, platform's
  10% becomes GST-inclusive (real commission 9.09%). Contradicts "10% + GST" wording. Rejected
  unless Turaboy directs otherwise.
- **Per-order rounding + pro-rata allocation:** one rounding step, but needs an allocation rule
  so per-session payouts still sum correctly — extra complexity and a remainder edge case. Rejected.
- **Keep fee-inclusive slice, no GST line (current code):** violates INV-6. Rejected.
