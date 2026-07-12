# Handoff — 2026-07-12 — Payments F-PAY-6 (GST tax invoice) complete · TRACK DONE

## Scope of this session
Sixth and final F-PAY milestone in one continuous session (F-PAY-1→6 all landed today).
Implemented the **provider GST tax invoice** (ADR-0002 §8.4). Backend only; committed on
`feat/F-PAY-1-connect-onboarding`. **The payments backend track is now complete.**

## What was done
- Persist the per-booking money split at confirm: `booking.commission_cents` +
  `commission_gst_cents` (alongside the existing `accrued_net_cents`), via `take_rate` in
  `_settle_confirmed`. Migration `a8d6e5f4b0c1` (round-trips clean). So gross =
  commission + GST + net is exact per line, immune to later fee/gst config changes.
- `booking.provider_tax_invoice(payment_id, organisation_id, actor_id)` → a `TaxInvoiceOut`:
  supplier = platform (commission + GST is the taxable supply), recipient = provider. Itemises
  only THIS org's **confirmed** lines in the order (multi-provider carts return just the caller
  org's lines; refunded/cancelled lines excluded — no standing taxable supply). Member-gated.
- Endpoint `GET /api/v1/booking/orders/{payment_id}/tax-invoice?organisation_id=X` (hosted in
  booking — it reads booking line-items, above payments in the layering). 403 non-member,
  404 when the org has no invoiceable line.
- Platform supplier identity: new deployment settings `JUGGLE_PLATFORM_LEGAL_NAME` /
  `JUGGLE_PLATFORM_ABN` (+ `.env.example`). Set the real ABN before charging in prod.

## Invariants touched
- **INV-6** (display vs invoice): the parent still sees only the GST-inclusive price; the
  commission/GST split is a provider-facing document. The invoice reconciles: per line,
  commission + commission_gst + net == gross == what the family paid.
- No money mutation (read-only), so no INV-1/INV-2 surface.

## Commands run + results
- `alembic upgrade head` → `a8d6e5f4b0c1`; downgrade→upgrade round-trips clean; single head.
- `make check` → ruff + mypy (150 files) + import-linter (2 kept) + pytest **189 passed**
  (4 new tax-invoice tests: totals/itemisation, membership 403, no-line 404, refunded excluded).

## Decisions made / deferred
- Read-only feature → no adversarial review this milestone (the money-mutation milestones
  F-PAY-2/3/5 each got one).
- Governance still open: ADRs 0001–0005 PROPOSED; CLAUDE.md vs CLAUDE2.md; `CLAUDE2.md` +
  `docs/juggle-prd-ext-1.md` uncommitted.

## Known issues & accepted risks
- Invoice granularity is **per (order, provider)**. A monthly/periodic statement is not built
  (out of scope; the per-order invoice is the discrete taxable-supply document).
- No PDF rendering — structured JSON only; the frontend renders it.
- `payment_surcharge_mode` (ADR-0003) never became a config key (surcharge is absorbed, so
  nothing reads it yet) — the string-kind `config.core.service` extension remains unbuilt,
  needed only if a pass-through surcharge is ever introduced.

## Git state — the whole payments track
Branch `feat/F-PAY-1-connect-onboarding`, **unpushed** (Rule 3). Commits this session (newest first):
- F-PAY-6 tax invoice (+ docs)
- F-PAY-5 payout clawback + release hardening (+ docs)
- F-PAY-3 webhook confirmation + auto-refund (+ docs)
- F-PAY-2 checkout settlement (GST take-rate + firm reservation) (+ docs)
- F-PAY-1 Connect onboarding backend + frontend (+ docs), F-PAY-0 ADRs
Migrations added: `b3f1c0a2d4e5`, `c4e2d1f0a6b7`, `d5a3b2c1e6f8`, `e6b4c3d2f7a9`,
`f7c5d4e3a8b9`, `a8d6e5f4b0c1` (head). Only `CLAUDE2.md` + `docs/juggle-prd-ext-1.md` uncommitted.

## Next session should
1. **Governance + push**: get Turaboy's ADR acceptance + the CLAUDE.md/CLAUDE2.md reconciliation,
   then push the branch / open the PR (Rule 3, needs approval). This is a large, green, coherent
   slice — good to review/merge before anything new.
2. **Frontend Stripe Payment Element**: the last piece to make live payments real end-to-end —
   use `OrderOut.client_secret` (already returned by checkout) on the Quasar checkout page,
   drop the FakeGateway sync-confirm flow for live mode, and add a provider "tax invoices" view
   hitting the new endpoint. Then a Playwright touch.
3. **Deferred hardening**: per-payout commit for `release_due_payouts` (the payout-release
   crash-window) once the worker has a real per-item commit path outside the test harness.

## Highest-risk thing to pressure-test
Now that the backend is complete, the sharpest remaining edge is the **payout-release
crash-window** (documented in the F-PAY-5 handoff): a Stripe transfer that sends but whose txn
rolls back, then re-sends a stale amount after an intervening clawback. Until per-payout commit
lands, don't let a clawback race an in-flight release in production.
