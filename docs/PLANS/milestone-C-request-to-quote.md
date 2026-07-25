# Plan — Milestone C: parties request-to-quote (PRD §9, ADR-0006 / ADR-0009)

Status: **DONE — 2026-07-25** (branch `feat/parties-request-to-quote`, behind the `party_quotes`
flag, OFF by default). Last piece of the ADR-0006 active gate — A, B, C, D are now all complete.

## The shape

Structured **brief** → provider **quote** → parent **accepts** → deposit. Per ADR-0009: expiry
default 72h (config, 12–336h), **exactly one** revision round, no free-text chat — the brief is
structured fields, the quote carries one message, the revision carries one message. That is the
entire comms surface.

State machine (ADR-0009): `sent → (revision_requested → revised)? → accepted | expired | withdrawn`.

## The money seam — the load-bearing decision

The operator deferred payments work. Milestone C's definition of done ends in a deposit, so the
design has to reach the deposit **without writing new money code**. It does:

> **A quote is a bespoke, unlisted `PartyPackage` + one `PartySlot`.** When a provider quotes, they
> create a private package (per-head price = the quoted price, `min_headcount == max_headcount ==`
> the agreed headcount) and a single slot at the agreed time. Accepting the quote calls the
> **existing, unchanged `parties.service.book_slot`**.

Consequences — all of these come free, with no new code and no new tests of money math:
- deposit % (ADR-0007) incl. the per-package override, and the deposit `PaymentIntent`;
- T-7d balance auto-charge (ADR-0008) and its retry/abandon handling;
- payout accrual and refund clawback (ADR-0010 / INV-5), and the provider GST tax invoice (F-PAY-6);
- **INV-1**: the slot is capacity-1 with the existing `FOR UPDATE` + partial-UNIQUE backstop, so two
  parents can't accept quotes onto the same time.

The one new thing this requires is keeping bespoke packages out of the marketplace: a
`PartyPackage.quote_only` flag (default `false`), excluded from every public listing query. Without
it a private quoted price would leak onto the public parties page.

**Rejected alternative:** a `quoted_total_cents` override passed into `book_slot`. It is the obvious
approach and it is wrong here — the override would have to flow through deposit, balance, payout,
clawback and invoice arithmetic, i.e. exactly the money paths that are deferred and that CLAUDE.md
requires an adversarial review to change.

## Scope

**Data** (`parties/core/models.py`)
- `PartyQuoteRequest` — the brief: guardian, organisation, event window, suburb, kid headcount,
  child **age band** (INV-3: ages only — never a name), optional budget, one notes field, status.
- `PartyQuote` — the offer: request, org, the bespoke `package_id` + `slot_id`, headcount,
  per-head + total snapshot, message, `expires_at`, `revision_count` (≤1), `revision_message`,
  `booking_id` (set on accept), status.
- Revisions happen **in place** on the quote row (bounded to one), not as new rows — the ADR caps
  negotiation at one round, so a history table would be storing a sequence that cannot exceed 2.

**Config (INV-11)** — `party_quote_expiry_hours`, default 72, bounded 12–336.

**Expiry** — `expire_due_quotes()` in the parties service, idempotent, run from the scheduler tick
alongside the other sweeps; notifies the parent and releases nothing (the slot was never held).

**Notifications** — one per transition, per ADR-0009.

**Flag** — everything behind `party_quotes`, **OFF by default**, exactly like `party_planner`: the
flow is email-driven and real email is not configured yet.

**Surfaces** — parent: request a quote from a provider, see quotes, request one revision, accept.
Provider: an inbox of briefs, quote/decline, revise once, withdraw.

## Invariants

- **INV-1** — accept goes through the unchanged `book_slot`; capacity-1 is the DB's job, not ours.
- **INV-2** — no new money movement; the deposit is the existing `payments` path.
- **INV-3** — the brief carries a child **age band and a kid count**, never a name or DOB. The free
  notes field is the one risk surface: the UI says "no kids' names", and nothing in the brief is
  copied into analytics events.
- **INV-6** — quoted prices are GST-inclusive, like every other displayed party price.
- **INV-11** — quote expiry is config, not a constant.
- **Non-goal fence (EXT-1 §10)** — one revision round, one message each way. No chat, ever.

## Definition of done

A parent submits a brief; the provider quotes with a price, time and inclusions; the parent requests
one revision; the provider revises; the parent accepts and lands on the **existing** deposit flow
with a real `PaymentIntent`; an unaccepted quote expires on the scheduler tick and notifies the
parent; a second revision request is refused; `make check` green; contracts KEPT.

## Outcome (2026-07-25)

All of the above, verified end to end against the running API in a rolled-back transaction:
brief → quote ($700) → counter → revised ($630) → **second round refused 409** → accept →
deposit $189 (the config 30%) → dev-confirm → `confirmed`; the bespoke package absent from
`/parties/packages`; all five transition emails sent.

22 backend tests (`tests/test_party_quotes.py`), including the ones that matter most: the
bespoke package never appears in either public listing, the revision cap holds from both sides,
an expired quote can't be accepted, an **accepted** quote survives the sweep, the superseded slot
is retired on revision/withdrawal/expiry, and the exact headcount band stops anyone booking the
bespoke slot directly at a different size.

Surfaces: `PartyQuotesPage.vue` (parent — enquiry form, quote card, one-revision ask, accept +
inline deposit) and a "Party enquiries" section on `ProviderOrgPage.vue` (inbox, quote/revise
dialog pre-filled from the brief, decline). Both hide themselves entirely when the flag is off.

**Deliberately not done:** no new payment code, per the money seam above — and therefore no
adversarial money review was needed. What did *not* get built: quote history (revisions replace
in place, capped at one), provider-side quote analytics, and any parent-facing "compare quotes
from several providers" view — a brief goes to one provider, as PRD §9 describes.
