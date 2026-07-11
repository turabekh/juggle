# Handoff — 2026-07-12 — Payments F-PAY-1 verified + committed (backend + frontend)

## Scope of this session
Picked up the prior handoff's outstanding gate: **F-PAY-1 backend was lint/type/contract-clean
but pytest had never run** (Docker/DB were down last session). This session verified it, fixed the
two real test failures it surfaced, committed the backend, then **built + committed the F-PAY-1
frontend** (provider payouts-setup UI) and updated `CLAUDE.md`. F-PAY-1 is now **DONE**.

## What was done
- **Brought the stack up**: `make db`, migrations `alembic upgrade head` applied cleanly
  (`b3f1c0a2d4e5` → `c4e2d1f0a6b7`, new head confirmed).
- **Ran the target tests** → 2 real failures in `test_connect_onboarding.py`
  (`test_account_updated_webhook_sets_flags`, `test_webhook_is_idempotent`). Root cause: the
  synthetic webhook payloads omitted the top-level `"object": "event"` field that every real
  Stripe event carries; **stripe 10+'s `construct_event` reads `event.object`** to distinguish
  v1/v2 events and raised `AttributeError`. Fixed in the **test fixtures** (added `"object":
  "event"`) — the fix belongs there because it makes the fixtures match real Stripe structure; no
  production code was wrong.
- **Full `make check` green**: ruff, mypy strict (150 files), import-linter (2 contracts kept),
  **161 pytest passed**.
- **Committed the backend**: branch `feat/F-PAY-1-connect-onboarding` off `main`. Split into
  clean commits: ADRs (F-PAY-0), F-PAY-1 backend, prior handoff doc.
- **Built the F-PAY-1 frontend** (was NOT started last session): a "Stripe payouts" panel in the
  provider org page Earnings section —
  - `api.ts`: `payments.connectStatus` / `connectOnboard` / `connectRefresh`
  - `types.ts`: `ConnectStatus`
  - `format.ts`: pure `payoutSetupDisplay(status)` mapping status → {chip color/label, hint,
    needsSetup, ctaLabel}; **5 Vitest cases** in `payoutSetup.test.ts`
  - `ProviderOrgPage.vue`: status chip (Not set up / In review / Active), a Set-up/Finish CTA that
    calls onboard then `window.location.href = link.url`, and an on-return refresh triggered by
    `?connect=return` that re-pulls flags and strips the query.
  - Verified via `make web-build` (vue-tsc + vite, green) and `make web-test` (20 units green).
- **Updated `CLAUDE.md`**: payments row now says separate charges & transfers (not destination
  charges) + gateway seam; status paragraph reflects the track being greenlit and F-PAY-0/1 done.

## Invariants touched (how respected / tested)
- **INV-2** (all Stripe in payments; idempotent webhooks): unchanged from last session; now
  **actually tested green** — real-HMAC `account.updated`, duplicate-delivery → `"duplicate"` with
  no double-apply, bad signature → 400.
- No new backend logic this session (only a test-fixture fix); INV-1/5/6 remain F-PAY-2…6.
- Frontend touches no invariant surface (read-only status + a redirect).

## Commands run + results
- `make db` → up; `alembic upgrade head` → applied b3f1c0a2d4e5, c4e2d1f0a6b7.
- `pytest tests/test_connect_onboarding.py tests/test_payouts.py -q` → **12 passed** (after fix).
- `make check` → ruff/mypy/lint-imports/pytest all green, **161 passed**.
- `make web-build` → vue-tsc clean + vite built. `make web-test` → **20 passed**.
- All commits are **local on `feat/F-PAY-1-connect-onboarding`**. Nothing pushed (Rule 3).

## Decisions made / deferred
- Made: fixed the webhook test fixtures (correctness, not a design change).
- **Still OPEN for Turaboy (unchanged from last session — need your call):**
  1. **ADRs 0001–0005 are PROPOSED** — accept or amend.
  2. **GST net formula** = `net = line − fee − gst` (provider nets ~89%). Veto if you want the
     platform to absorb commission-GST (`net = line − fee`).
  3. **Merchant-of-record (O-1)** legal/terms dependency is now real per ADR-0001.
  4. **CLAUDE.md vs CLAUDE2.md governance** — still two files. I kept treating CLAUDE2's
     invariants/process as binding while keeping the repo's real structure + docstrings. Reconcile.
     (`CLAUDE2.md` and `docs/juggle-prd-ext-1.md` remain **uncommitted** pending this.)

## Known issues & accepted risks
- Config keys `gst_rate` + `payment_surcharge_mode` still not in the registry (land with F-PAY-2);
  `payment_surcharge_mode` is a string enum and needs a small `config.core.service` extension.
- The onboarding redirect leaves the SPA, so it isn't covered by an e2e; the display logic is
  unit-tested instead. A Playwright happy-path against `FakeGateway` could be added later.
- Branch not pushed; no PR (awaiting approval per Rule 3).

## Next session should
1. **Get Turaboy's call on the four open decisions above** before F-PAY-2 (they shape it).
2. **Plan F-PAY-2 (checkout PaymentIntent) first** — write the plan, run `plan-critic` on the
   concrete diff. It must implement **ADR-0005**: firm reservation (seat stays counted to a
   *terminal* outcome), **card-only** (synchronous), webhook-driven confirm, session-row lock +
   **auto-refund if the seat is truly gone**, PI carries no `application_fee_amount`/`transfer_data`.
3. Add `gst_rate` + `payment_surcharge_mode` config keys (+ the string-kind config extension).
4. Only then implement, with the race-ordering integration tests written first.

## Highest-risk thing to pressure-test
Unchanged and now imminent: **the webhook-vs-seat reconciliation in F-PAY-2/3**. Firm-reservation
+ session-row lock + auto-refund-on-lost-seat is the core correctness bet of the payments track.
An oversell or a stranded paid seat is one race away the moment confirm becomes webhook-driven.
