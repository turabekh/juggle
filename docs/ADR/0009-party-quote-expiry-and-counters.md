# ADR 0009 — Party quote expiry + counter-offers (D-07)

- Status: **ACCEPTED** (Turaboy, 2026-07-12)
- Date: 2026-07-12
- Invariants touched: INV-11 (config); non-goal: no chat (EXT-1 §10)
- Related: ADR-0006, PRD §9 (request-to-quote); ADR-0007 (deposit rails reused on accept)

## Context
Request-to-quote parties (mobile entertainers) run a **structured brief → provider quote → parent
accepts → deposit** flow (Milestone C). Quotes must expire (stale prices/availability) and we must
decide whether haggling is allowed — the risk being that "negotiation" becomes a chat channel, which
is an explicit non-goal.

## Decision
- **Quote expiry default = 72h** (config `party_quote_expiry_hours`, bounded 12–336h). On expiry the
  quote → `expired`; the parent must re-request.
- **Counter-offers: the parent may request one revision** ("can you do it for X / add Y?"), and the
  provider may issue **one revised quote** in response. After that, it's accept or let it expire — **no
  open-ended back-and-forth.** This caps negotiation at one round, keeping it structured, not a chat.
- **No free-text chat:** the brief is structured fields; the quote carries a single message field and
  the revision carries a single message field. That's the entire comms surface.
- **State machine:** `draft → sent → (revision_requested → revised)? → accepted | expired | withdrawn`.
  Notifications on each transition. Accepting reuses the ADR-0007 deposit rails.

## Consequences
- One-round counters cover the common "tweak the package/price" case without opening a messaging
  product (non-goal) or a haggling loop.
- Expiry keeps quoted prices/availability honest and bounds provider obligation.

## Alternatives considered
- **Unlimited counters.** Rejected: becomes chat/haggling — a non-goal, and a moderation/abuse surface.
- **No counters (accept-or-nothing).** Rejected: too rigid for bespoke party quotes where a small tweak
  is normal; one round is the pragmatic middle.
