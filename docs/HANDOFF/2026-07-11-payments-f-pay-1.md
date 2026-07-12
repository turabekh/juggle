# Handoff — 2026-07-11 — Payments track (Stripe Connect), F-PAY-0 + F-PAY-1 backend

## Scope of this session

Kicked off the **Payments track (MVP)** — Stripe Connect, end to end — per the task brief:
provider Connect Express onboarding; checkout PaymentIntent; idempotent webhooks; refunds
+ INV-5 auto-refund; payout release + admin holds + reconciliation; GST tax invoice.
Milestones **F-PAY-1…6** (separate commit chains). This session completed **F-PAY-0**
(decisions + ADRs + plan-critic) and the **backend of F-PAY-1** (Connect onboarding).

**Payments were previously deferred**; this task explicitly greenlit them. Direction change
is intentional and recorded here.

## What was done

### F-PAY-0 — decisions + ADRs + plan-critic (COMPLETE)
- Resolved the four gated decisions with the user (all came back as the recommended option):
  - **Q1 charge model → separate charges & transfers** (platform charges card on its own
    balance, keeps 10% by not transferring it, `Transfer` per session at T+N; admin can hold
    one session's payout). Makes the platform **merchant of record** → **O-1 (platform terms)
    is now a live legal dependency** (flagged, non-blocking for the build).
  - **Q2 take-rate → 10% fee-exclusive + GST, per-session rounding.**
  - **Q3 surcharge → absorbed** (no pass-through; single GST-inclusive price).
  - **Q4 payout timing → T+2** after session completion.
- Wrote **ADR 0001–0005** (all **PROPOSED**, awaiting Turaboy acceptance) + `docs/ADR/README.md`:
  - 0001 charge model; 0002 take-rate; 0003 surcharge; 0004 payout timing;
  - **0005 checkout settlement** — captures the plan-critic's INV-1/INV-2 redesign.
- **GST math correction (needs your veto if wrong):** ADR-0002 originally wrote
  `net = line − fee`. The plan-critic caught that this contradicts "10% **+ GST**". Resolved
  from the PRD/INV-6 wording as **`net = line − fee − gst`** (provider nets ~89%; platform
  keeps `fee` as revenue and remits `gst` to the ATO). Recorded as ADR-0002 rev.2. If you want
  the platform to *absorb* the commission-GST instead (`net = line − fee`), say so and I'll flip it.
- Ran **plan-critic** (adversarial) on the INV-1/INV-2 surfaces. 14 findings; the load-bearing
  ones are now design constraints in ADR-0005 and must shape F-PAY-2/F-PAY-3:
  1. **Firm the seat, don't leave an expiring hold** — a late/async `payment_intent.succeeded`
     after the hold TTL oversells or strands the paid seat. MVP = **card-only** (synchronous);
     seat stays counted until a *terminal* outcome; success handler locks the session row and
     **auto-refunds if the seat is truly gone**.
  2. **`payment_failed` is non-terminal** — a retry can still succeed on the same PI; release
     seats only on `payment_intent.canceled` or an abandoned-checkout sweep.
  3. **One atomic transaction per webhook event** — `UNIQUE(event_id)` necessary but not
     sufficient; dedupe-insert + side effects + processed-marker commit together, with
     `FOR UPDATE` on the `Payment` row.
  4. **Refunds must reverse payouts** — under separate charges a refund after a released
     `Transfer` needs a **Transfer Reversal**; `release_due_payouts` needs `SKIP LOCKED` +
     per-payout commit + a `payout.id` Stripe idempotency key (F-PAY-5).
  5. **Accrue payout on charged quantity (`hold.quantity`)**, not a live child count (a child
     deleted between checkout and confirm — APP deletion is shipped — would under-accrue).
  Full register is in this session's transcript; the summary above + ADR-0005 are the durable copy.

### F-PAY-1 — Connect Express onboarding (BACKEND COMPLETE, tests UNRUN; frontend NOT started)
Real Stripe lives behind the existing `PaymentGateway` Protocol; `FakeGateway` still backs all
non-Stripe tests. `get_payment_gateway()` returns `StripeGateway` iff `JUGGLE_STRIPE_SECRET_KEY`
is set, else the fake — so local/CI need no Stripe account (INV-2 seam intact).

**New files**
- `docs/ADR/0001…0005*.md`, `docs/ADR/README.md`
- `apps/api/alembic/versions/b3f1c0a2d4e5_add_org_stripe_connect_flags.py` — org `charges_enabled`
  / `payouts_enabled` (bool, server_default false then dropped). down_revision `8b9699333869`.
- `apps/api/alembic/versions/c4e2d1f0a6b7_add_stripe_event_ledger.py` — `stripe_event` table,
  UNIQUE(event_id). down_revision `b3f1c0a2d4e5`. **New head = `c4e2d1f0a6b7`.**
- `apps/api/tests/test_connect_onboarding.py` — 7 tests: onboarding creates account+link;
  refresh enables caps; membership-gated; account.updated webhook sets flags (REAL HMAC
  signature, never mocked); webhook idempotent (duplicate → "duplicate", no double-apply);
  bad signature → 400; payout gated on payouts_enabled.

**Modified files**
- `apps/api/pyproject.toml` — `+ "stripe>=10.0"`.
- `apps/api/src/juggle/settings.py` — `stripe_secret_key` / `stripe_publishable_key` /
  `stripe_webhook_secret` (JUGGLE_-prefixed; blank ⇒ FakeGateway).
- `.env.example` — `JUGGLE_STRIPE_*` placeholders + note that the Stripe CLI reads its own
  `STRIPE_API_KEY`; webhook path `POST /api/v1/payments/webhook`.
  > **Superseded in F-PAY-3:** the single Stripe webhook endpoint moved to
  > `POST /api/v1/booking/stripe/webhook` (settlement orchestrates booking). Use that URL.
- `apps/api/src/juggle/modules/org/core/models.py` — `charges_enabled`, `payouts_enabled` cols.
- `apps/api/src/juggle/modules/org/core/service.py` — `get_org_by_stripe_account`,
  `set_stripe_account`, `set_connect_flags`.
- `apps/api/src/juggle/modules/payments/core/gateway.py` — Protocol gains
  `create_connect_account` / `create_account_link` / `retrieve_account` (+ result dataclasses);
  new `StripeGateway` (**separate charges: PI has NO `application_fee_amount`, NO
  `transfer_data.destination`; `payment_method_types=["card"]`**); env-based selection.
- `apps/api/src/juggle/modules/payments/core/models.py` — `StripeEvent` (webhook dedupe ledger).
- `apps/api/src/juggle/modules/payments/core/service.py` — `start_onboarding`, `connect_status`,
  `refresh_account_status`, `_record_event` (**SAVEPOINT/`begin_nested` so a duplicate-key
  rollback doesn't nuke the surrounding txn — matters in the shared-session test harness too**),
  `_handle_account_updated`, `handle_webhook` (verify raw body → dedupe → dispatch account.updated);
  **`release_due_payouts` now gated on `payouts_enabled` + non-null `stripe_account_id`** and
  returns the actually-released count.
- `apps/api/src/juggle/modules/payments/core/schemas.py` — Onboard/ConnectStatus/Refresh/Webhook schemas.
- `apps/api/src/juggle/modules/payments/ui/routes.py` — `POST /payments/connect/onboard`,
  `GET /payments/connect/status`, `POST /payments/connect/refresh`, `POST /payments/webhook`
  (raw-body signature verify), alongside the existing payouts/payment reads.
- `apps/api/tests/test_payouts.py` — `_org_with_session` now onboards + refreshes the org so
  payouts can release under the new gate (the gate is why this change was needed).

## Invariants touched (how respected / tested)
- **INV-2 (all Stripe in payments; idempotent webhooks):** every Stripe call is in
  `payments/core/gateway.py` or the webhook handler; `stripe_event` UNIQUE(event_id) + SAVEPOINT
  dedupe. Tested: `test_webhook_is_idempotent`, `test_webhook_rejects_bad_signature` (real HMAC).
- **INV-11 (config-driven):** `payout_delay_days` (existing) still governs T+N; new keys
  `gst_rate` + `payment_surcharge_mode` are specced in ADR-0002/0003 but **not yet added to the
  config registry** (that lands with F-PAY-2 where checkout/invoice use them).
- **INV-1 / INV-5 / INV-6:** NOT touched by F-PAY-1 code yet — they are F-PAY-2…6. ADR-0005
  is the design of record for INV-1; must be implemented there.
- Connect gating (finding #13): `release_due_payouts` skips providers not `payouts_enabled`.
  Tested: `test_payout_gated_on_payouts_enabled`.

## Commands run + results
- `uv run ruff check .` → **All checks passed.**
- `uv run mypy src` → **Success: no issues in 150 source files.** (One localized
  `# type: ignore[no-untyped-call]` on `stripe.Webhook.construct_event` — Stripe ships it untyped.)
- `uv run lint-imports` → **2 kept, 0 broken.**
- `uv run alembic upgrade head` → **FAILED: DB unreachable** (Postgres not running).
- `make db` → **FAILED: Docker daemon not running.**
- `pytest` → **NOT RUN** (needs the DB). This is the one gate still outstanding.

## Decisions made (ADR refs) / deferred
- Made: ADR-0001..0005 (PROPOSED). GST net formula resolved to `net = line − fee − gst`.
- Governance still open: **CLAUDE.md vs the new CLAUDE2.md.** I'm treating CLAUDE2's invariants
  (INV-1..13), process (ADR/plan-critic/handoff), and `feat(F-PAY-n)` commits as binding, keeping
  the repo's actual structure + docstrings, and NOT retroactively stripping comments or renaming
  modules. Confirm or reconcile the two files.
- Deferred (correctly): `gst_rate` + `payment_surcharge_mode` config keys (F-PAY-2); the whole
  checkout/webhook/refund/payout redesign per ADR-0005 (F-PAY-2..6).

## Known issues & accepted risks
- **pytest never ran** — backend is lint/type/contract-clean but behaviourally UNVERIFIED. Do
  NOT commit F-PAY-1 until pytest is green. Migrations are also unapplied to any DB.
- **Config registry only allows int/float settings.** `payment_surcharge_mode` is a string enum;
  adding it (F-PAY-2) needs a small extension to `config.core.service` (a `str` kind + allowed
  values) — plan for it, it's not free.
- **Merchant-of-record (O-1)** is now real per ADR-0001 — external legal/terms dependency.
- **Environment fragility this session:** the disk hit 100% (blocked all file writes); cleared
  ~7 GB of regenerable caches (uv/yarn/pip/pypoetry/Chrome/Telegram). Docker Desktop was down and
  slow to boot. Both are environmental, not code.

## Git state
- Branch: **main** (NOT branched — should be `feat/F-PAY-1-connect-onboarding` before committing).
- **All changes are uncommitted** in the working tree. They persist across a restart. Nothing to
  stash. Reason for not committing: pytest unverified (Rule 5 — payment paths need integration
  tests before merge).

## Next session should (in order)
1. `open -a Docker` (or start Docker Desktop), wait for `docker info` to succeed, then
   `cd /Users/turaboy/projects/jungler && make db`.
2. `cd apps/api && uv run alembic upgrade head` (applies b3f1c0a2d4e5 + c4e2d1f0a6b7; new head
   `c4e2d1f0a6b7`). If the dev DB has stale seeded data, reseed: `alembic downgrade base &&
   alembic upgrade head && make seed` (from repo root use the make targets).
3. `uv run pytest tests/test_connect_onboarding.py tests/test_payouts.py -q` — fix any failures.
   Watch especially: the SAVEPOINT dedupe under the shared-session harness, and the FakeGateway
   `retrieve_account` returning enabled=True (that's what `refresh` relies on).
4. Full `make check`. Then **branch + commit F-PAY-1 backend** as `feat(F-PAY-1): Connect Express
   onboarding + account.updated webhook + payout gating`.
5. **Finish F-PAY-1 frontend** (not started): `apps/web` provider org page — a "Set up payouts
   (Stripe)" button calling `POST /payments/connect/onboard` then redirecting to the link, a
   status chip from `GET /payments/connect/status`, and a refresh on return. Add `api.ts` methods.
   Then a Playwright/Vitest touch. Commit separately.
6. Update `CLAUDE.md` (payments section) once F-PAY-1 is committed.
7. Only then start **F-PAY-2** (checkout) — and implement it to ADR-0005 (firm reservation,
   card-only, webhook-driven confirm, session-lock + auto-refund-on-lost-seat). Run plan-critic
   again on the concrete F-PAY-2 diff before merging.

## Highest-risk thing to pressure-test
The **webhook-vs-seat reconciliation in F-PAY-2/3** (ADR-0005 / plan-critic #1–#4): the moment
confirmation becomes webhook-driven, an oversell or a stranded paid seat is one race away. The
firm-reservation model + session-row lock + auto-refund-on-lost-seat is the core correctness bet
of the whole payments track — build it deliberately, with the race-ordering integration tests,
before anything downstream.
