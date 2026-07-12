# Plan — "Always-on marketplace" release (ADR-0006)

Status: **PROPOSED — awaiting approval of ADR-0006 before any feature code.**
Sequence: Step 0 (re-gate docs) → A → B → C → D, separate branch + PR per milestone.
Governance: `plan-critic`-style adversarial review before B and C (money paths); security review on
invite/RSVP surfaces + the balance-charge job; migration review per migration; integration tests
mandatory on deposit/balance/adjustment (Stripe CLI fixtures, never mocked signatures); Playwright
e2e per milestone; everything via compose; **never push without asking**; handoff doc per session.

> **Available-subagent note:** `plan-critic` / `decision-advisor` / `security-scanner` /
> `migration-guard` aren't real agent types in this environment. We use the proven pattern from the
> payments track: an adversarial **general-purpose review subagent** on each money/inventory/child-data
> diff before merge, and one focused ADR per decision below. Naming kept for continuity.

## Step 0 — Re-gate (docs-only, before any feature code)
- **ADR-0006** (this initiative's decision) — written, PROPOSED. **Blocks everything until accepted.**
- On acceptance: restore a concise **Phase gates** section to `CLAUDE.md` and record the re-gate
  (parties/E2/G2 → active); update **PRD-EXT-1 §9** sequencing; update the **README** positioning line.
- Reaffirm the term-enrolment fence verbatim (EXT-1 §10) in CLAUDE.md's non-goals.
- Depends on PR #1 merging first (it introduces PRD-EXT-1 + the CLAUDE.md reconciliation).

## Milestone A — E2 broadened: any-day one-off sessions (surfaces, not schema)
Sessions already accept arbitrary dates — this is surface + moderation work.
- **Feeds:** "This weekend" and "After school this week" bookable feeds; weekend/weekday filters and a
  day-of-week facet in `search`.
- **Moderation guardrail (EXT-1 §2-E2, §10):** listing-policy hook — one-off/drop-in only;
  recurring-enrolment listings rejected at moderation with a reason code (admin console flag).
- **SEO:** route stubs per surface (real SSR lands in the SSR track).
- Invariants: **INV-8** (feeds read the live inventory projection), **INV-12** (any "filling fast" is real).
- Tests: search-facet + feed unit/integration; a moderation-rejection test for a recurring-enrolment listing.

## Milestone B — Parties: instant-book mode (PRD §9) — MONEY PATH
- **New listing type `party_package`** on a venue: venue-defined bookable **slot calendar** (each slot is
  capacity-1 inventory — INV-1 hold/confirm atomicity applies), package picker, per-head pricing with
  min/max headcount.
- **Money flow (all inside `payments`, extends F-PAY, INV-2):**
  - **Deposit %** captured at booking (partial capture on the PaymentIntent);
  - **Balance auto-charged at T-7d** via a scheduled job (idempotent, off-session charge);
  - **Guest count adjustable until T-72h** → delta charge or partial refund (reuses F-PAY-5 partial-refund
    + clawback rails).
- **Party config knobs (INV-11):** default deposit %, balance-charge offset, adjustment cutoff, weather-
  clause toggle for outdoor venues — all via `config`.
- Invariants: **INV-1** (slot capacity), **INV-2** (webhooks idempotent; off-session balance charge),
  **INV-6** (GST-inclusive display incl. per-head), **INV-5/D-08** (refund floor incl. deposits), **INV-11**.
- Tests: integration on deposit → adjust → balance-charge (clock-controlled), Stripe CLI fixtures.
  Adversarial review before merge.

## Milestone C — Parties: request-to-quote mode — MONEY PATH
- Structured **brief** → provider **quote** (price, inclusions, expiry) → parent **accepts** → deposit via
  Milestone B rails.
- **Quote state machine:** draft / sent / accepted / expired / withdrawn; notification on each transition.
- **No free-text chat** (non-goal §10): structured brief fields + a single quote message field only.
- Invariants: as B, plus the quote-expiry job (idempotent). Adversarial review before merge.

## Milestone D — G2: party invites + RSVP (ships WITH parties, not before)
- Host generates an invite page from a party booking; **guests RSVP without accounts**; headcount syncs to
  the booking respecting the T-72h rule.
- **INV-13 hard requirements:** no child names in URLs/params/analytics; child first name in invite copy
  only via per-instance **host opt-in**; guest emails are transactional-only for that party; a **separate
  explicit marketing opt-in** checkbox at RSVP (Spam Act 2003); **no public guest lists**.
- Post-RSVP: "powered by Juggle" + an age-relevant discovery teaser — any scarcity shown is live inventory
  (**INV-12**).
- Security review on the invite/RSVP surface (unauthenticated, child-adjacent). Playwright e2e: invite → 12
  RSVPs leaking zero child PII.

## Decisions to resolve FIRST (one ADR each — draft recommendations)
- **D-05 — deposit % default + bounds.** Recommend **30%**, bounded **10–100%** (config, INV-11).
- **D-06 — balance-charge failure at T-7d.** Recommend: retry schedule (e.g. 3 attempts over 48h) → host
  notified on each failure → if still failing by T-72h, provider notified + booking auto-cancelled with
  deposit handled per D-08. Needs a decision pass.
- **D-07 — quote expiry + counter-offers.** Recommend expiry default **72h**; venues may counter-offer
  **once** (bounded, to avoid haggling/chat creep — chat is a non-goal).
- **D-08 — party refund floor vs deposits + weather clause.** Recommend: **yes**, INV-5 extends — provider
  cancels ⇒ 100% refund **including deposit**, always; the weather clause only **reschedules** (never a
  platform-side forfeiture of the parent's money).

## Definition of done (whole initiative)
A parent books a party slot with a 30% deposit, adjusts headcount at T-96h, the balance auto-charges at
T-7d, and 12 guests RSVP through an invite page that leaks zero child PII; a quote-mode entertainer sends a
quote that expires correctly; weekday drop-in sessions appear in "After school this week"; a recurring-class
listing attempt is rejected at moderation; `make check` green, import-linter contracts KEPT, e2e green.
