# ADR 0003 — Card surcharge: absorbed (no pass-through) at MVP

- Status: **PROPOSED** (awaiting Turaboy acceptance)
- Date: 2026-07-11
- Invariants touched: INV-6 (GST-inclusive single price), INV-11 (config)
- Related: PRD §7.4, D-03; ACCC surcharging rules (surcharge ≤ cost of acceptance)

## Context

D-03: pass Stripe's card-processing cost through to the parent as a surcharge line, or
absorb it into the platform's 10% take. ACCC rules permit surcharging only up to the
**actual cost of acceptance**, and require it be provable and itemised.

## Decision

**Absorb** card fees at MVP. Checkout shows a **single GST-inclusive price** with no
surcharge line. The card cost (~1.7% + A$0.30) comes out of the platform's 10% take.

Surcharge mode is a **config lever** (INV-11) so it can change without a deploy:

- **`payment_surcharge_mode`** — NEW config value, `"absorb"` (default) or `"surcharge"`.
  Stored as a bounded enumerated string. At MVP only `"absorb"` is implemented end-to-end;
  the config key exists so switching later is a config change + a checkout code path, not
  a schema change.

## Consequences

- Cleanest ACCC component-pricing compliance and best conversion — the parent sees one
  number that matches the listing (reinforces INV-6 and INV-8/12 honesty posture).
- Platform margin absorbs processing cost; acceptable within the 10% take at MVP volumes.
- No "cost of acceptance" figure to compute, justify, or police at MVP.
- Config key is present but the `"surcharge"` branch is **not built** (out of scope, no
  scaffolding beyond the config enum) until a deliberate later decision.

## Alternatives considered

- **Pass-through surcharge:** protects full margin, but adds an itemised surcharge line,
  an ACCC cost-of-acceptance calculation that must stay provably ≤ true cost, and a
  noisier checkout. Deferred; revisit if card costs materially erode the take.
