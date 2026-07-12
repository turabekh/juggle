# Handoff — 2026-07-12 — Frontend Stripe Payment Element (live checkout)

## Scope of this session
After completing the payments backend (F-PAY-1…6), wired the **frontend Stripe Payment
Element** so live card payments work end to end. Committed on `feat/F-PAY-1-connect-onboarding`.

## What was done
### Backend
- Public `GET /api/v1/payments/config` → `{ live, publishable_key }` (`PaymentConfigOut`).
  `live` = a Stripe secret key is set; `publishable_key` is not secret. Declared before the
  `GET /payments/{payment_id}` param route so it matches first.

### Frontend
- `@stripe/stripe-js@^4` dependency (loads `js.stripe.com` at runtime via `loadStripe`, so it
  never enters the bundle — build size unchanged).
- `api.payments.config()` + `api.payments.status(id)`; `Order` type gains `client_secret` +
  `fee_gst_cents`; new `PaymentConfig` / `PaymentStatus` types.
- **`StripePaymentPanel.vue`**: loads Stripe, mounts the Payment Element from a
  `client_secret`, on pay calls `confirmPayment(redirect: 'if_required')`, then — because the
  booking is confirmed server-side by the webhook — **polls `GET /payments/{id}`** until it
  settles (`succeeded`/`failed`/timeout→`pending`) and emits `paid`/`failed`/`pending`.
- **`CheckoutPage.vue`** branches on `config`:
  - **live**: "Continue to payment" creates the order (checkout → `client_secret`), then shows
    the Payment Element; on `paid` clears the cart → bookings. 3DS redirects return to
    `/checkout?pid=…`; on mount, `?pid=…&redirect_status=…` resumes the poll.
  - **dev / FakeGateway** (no keys): the existing one-click sync-confirm flow is kept
    (`payDev` = checkout + confirm).

## Verified
- Backend `make check` → **190 passed** (incl. a `test_payment_config` for dev mode).
- Frontend `vue-tsc` clean, `vite build` green, **20 Vitest** green.
- Live-API smoke (dev/FakeGateway): `config` → `{live: false, publishable_key: null}`; checkout
  returns a `client_secret` + `fee_gst_cents`; `GET /payments/{id}` returns exactly the poller's
  shape (`id, status, amount_cents, application_fee_cents, fee_gst_cents, currency`); dev confirm
  → `succeeded`. So the whole data contract the Payment Element consumes is confirmed.

## Known issues & accepted risks
- **The live Payment Element path itself is unexercised** — rendering the real card form + a real
  `confirmPayment` needs **Stripe test keys** (set `JUGGLE_STRIPE_SECRET_KEY` /
  `_PUBLISHABLE_KEY` / `_WEBHOOK_SECRET`, run `stripe listen --forward-to
  localhost:8000/api/v1/booking/stripe/webhook`, pay with `4242…`). The code is structurally
  correct and the dev fallback + API contract are verified, but book a manual test-key run before
  relying on live payments. No Playwright e2e for the live path (can't without keys).
- **No provider tax-invoice UI yet** — the endpoint (`GET /booking/orders/{id}/tax-invoice`)
  exists; a provider-facing "invoices" view is a small follow-up.
- The dev smoke committed a few throwaway rows to the local dev DB (harmless; `make seed`/reset
  clears them).

## Git state
- Branch `feat/F-PAY-1-connect-onboarding`, **unpushed** (Rule 3). One feat commit
  (`feat(F-PAY): frontend Stripe Payment Element on checkout`) + this docs commit. Still only
  `CLAUDE2.md` + `docs/juggle-prd-ext-1.md` uncommitted (governance).

## Next session should
1. **Governance + push**: ADR acceptance + CLAUDE.md/CLAUDE2.md reconciliation, then push / PR the
   whole branch (F-PAY-0…6 + frontend).
2. **Manual live-key test** of the Payment Element (checklist above), then a Playwright e2e gated
   on test keys being present.
3. Small follow-ups: provider tax-invoice view; the deferred per-payout commit for payout release.

## Highest-risk thing to pressure-test
The **live Payment Element ↔ webhook handoff**: client confirms the PaymentIntent, but the booking
only flips to confirmed when `payment_intent.succeeded` arrives and settles. The poll tolerates lag
(20×1.5s → "pending" message), but verify with real test keys that (a) a normal card confirms and
the poll catches it, and (b) a 3DS card redirects to `/checkout?pid=…` and resumes correctly.
