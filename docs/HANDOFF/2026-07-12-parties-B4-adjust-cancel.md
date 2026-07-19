# Handoff — 2026-07-12 — Parties B4 (adjust + cancel) complete · parties money model DONE

## Scope
Built **Milestone B4** — guest-count adjustment + provider/parent cancellation with payout
clawback (ADR-0008/0010). Adversarially reviewed; **2 money should-fixes found + fixed**. This
**completes the parties money model B1–B4**. On branch `feat/B-parties-decisions` (PR #5).

## What was done
- **`adjust_headcount`** (guardian, confirmed + pre-capture, before T-72h): recompute the total;
  refund any now-excess deposit (partial); the later balance charge collects the rest.
- **`cancel_booking`** (parent or provider member, ADR-0010): **provider ⇒ 100% refund incl.
  deposit**; **parent ⇒ keeps at most the deposit** (refund the balance if captured); releases the
  slot; both row-lock the booking; host is emailed.
- **Payout clawback** reduces the party payout to the provider's net on the **retained** amount
  (computed by subtraction → reconciles exactly to `net(total)`), targeting `booking.payout_id`.

## Adversarial review — 2 money should-fixes fixed
- **Rounding partition leak:** the naive `net(refunded)` clawback left the provider
  `net(total)−net(balance)`, which ≠ `net(deposit)` under banker's rounding (net is non-additive) —
  a cent leaked either direction. → clawback = `net(total) − net(retained)`, exact. Locked by
  `test_parent_cancel_clawback_is_exact_under_rounding` (per-head 501 edge → payout ends at 2230,
  not the buggy 2229).
- **Uncaptured-deposit refund:** provider-cancelling a still-`pending` deposit refunded an
  uncaptured PI (500 in prod). → deposit refund gated on `succeeded`. Locked by a pending-deposit
  provider-cancel test.
- Nits fixed: **parent-first precedence** (a guardian who's also an org member forfeits per parent
  rules, not provider), **fail-closed** adjustment cutoff, decoupled deposit clamp, host email.

## Verification
`make check` **226 passed** (27 parties tests); mypy strict; contracts kept. All three parties
money milestones (B2/B3/B4) went through the adversarial-review gate — it caught **6 blockers/
should-fixes across them** (2 in B2-era via B1 review, 2 in B3, 2 in B4), all fixed before commit.

## Known gaps / next
- **Provider-side cancel notification** still not sent (host is now emailed; provider gets an
  event only) — small follow-up.
- Party **Payments carry no per-booking fee/GST split** (0/0; the split lives in the payout net) —
  reporting-only.
- **Frontend for parties** (provider package/slot management + parent party booking + adjust/cancel,
  with the Payment Element for the deposit) is NOT built — the natural next surface.
- **Live Stripe test-key run** is still required for the off-session balance path (B3) and the
  deposit Payment Element — FakeGateway can't model a real `CardError`/3DS.
- **Milestone C** (request-to-quote parties, ADR-0009) and **D** (party invites+RSVP, G2/INV-13)
  remain per ADR-0006's A→B→C→D plan.

## Git / PR
PR #5 (`feat/B-parties-decisions`) = decisions 0007–0010 + B1 supply + B2 deposit + B3 balance +
**B4 adjust/cancel**. Stacked chain #1→#5, all green. Merge order #1→#2→#3→#4→#5.

## Highest-risk thing to pressure-test
The **live off-session money paths** (B3 balance charge, B4 adjustment delta if extended) with real
Stripe test keys — declines, 3DS, and the retry/cancel/refund/clawback reconciliation end to end.
