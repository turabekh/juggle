# Handoff — 2026-07-25 — Milestone C: parties request-to-quote

Second session of the day. Branch **`feat/parties-request-to-quote`** (base `main` @ `b2645e2`,
nothing pushed). Read `CLAUDE.md`, then `2026-07-25-status-audit-and-planner-fixtures.md` (the
earlier session), then this.

---

## 1. TL;DR

**Milestone C is done, which closes the ADR-0006 active gate** — A, B, C and D are all complete.
A parent sends a structured brief, the provider replies with a priced quote, one revision round is
allowed, and accepting takes a deposit and books the date.

**No new money code was written.** That was the constraint (payments work is deferred) and it drove
the whole design — see §2. `make check`: **337 passed, 0 failed**, contracts KEPT, `vue-tsc` clean,
web build green, 27 Vitest units pass.

Everything is behind the **`party_quotes` flag, OFF by default**, exactly like `party_planner`: the
flow is email-driven end to end and real email still isn't configured.

---

## 2. The load-bearing decision — how accept reaches a deposit without touching money code

> **A quote *is* a bespoke, unlisted `PartyPackage` + one `PartySlot`.**

When a provider quotes, the service creates a private package (per-head price = the quoted price,
`min_headcount == max_headcount ==` the agreed headcount) and a single slot at the agreed time.
Accepting calls the **existing, unchanged `parties.service.book_slot`**.

What that buys, for free and untested-by-me because it was already tested:
- the deposit % (ADR-0007, including the per-package override) and the deposit `PaymentIntent`;
- the T-7d balance auto-charge (ADR-0008) with its retry/abandon handling;
- payout accrual, refund clawback (ADR-0010 / INV-5), and the provider GST tax invoice (F-PAY-6);
- **INV-1** — the bespoke slot is capacity-1 with the same `FOR UPDATE` + partial-UNIQUE backstop
  instant-book relies on, so a quoted date can only ever be sold once.

The obvious alternative — passing a `quoted_total_cents` override into `book_slot` — was rejected:
that override would have to flow through deposit, balance, payout, clawback and invoice arithmetic,
i.e. precisely the deferred money paths, and CLAUDE.md requires an adversarial review to change them.

**The one risk this design creates** is a private price leaking onto the marketplace, so
`PartyPackage.quote_only` (default false) is excluded from both public listing queries, and a test
asserts the bespoke package appears in neither.

---

## 3. What shipped

**Backend** (all inside the existing `parties` module — no new module, so the layering is untouched)
- `parties/core/models.py` — `PartyQuoteRequest` (the brief), `PartyQuote` (the offer),
  `PartyPackage.quote_only`. A partial UNIQUE gives **one live quote per brief**; a CHECK caps
  `revision_count` at 1 as the DB backstop to ADR-0009's one-round rule.
- `parties/core/quotes.py` — the service: create/withdraw a brief, send/revise/withdraw a quote,
  request a revision, decline, accept, and the expiry sweep.
- `parties/ui/quote_routes.py` — 10 routes under `/api/v1/parties/quotes`, flag-gated.
- `config` — `party_quote_expiry_hours` (72, bounded 12–336) per ADR-0009. **INV-11**: expiry is
  config, not a constant.
- `notifications` — one email per transition (requested / received / revision-requested / accepted /
  closed). Bodies carry the party's *shape* — date, kid count, price — never a child's name.
- `scheduler` — `expire_due_quotes` in the tick; `JobSummary.quotes_expired`.
- Migration `61452b91bbf6`. **Note:** autogenerate produced a `NOT NULL` `quote_only` with no
  server default, which would have failed against every existing package row (prod has live ones) —
  fixed to `server_default=sa.false()` and verified against the 15 packages in the dev DB.

**Frontend**
- `PartyQuotesPage.vue` (`/parties/quotes`) — enquiry form, quote card with expiry, the one-revision
  ask, accept, and the deposit settled **inline** with the same `StripePaymentPanel` /
  dev-confirm pair instant-book uses.
- `ProviderOrgPage.vue` — a "Party enquiries" section: inbox, a quote dialog pre-filled from the
  family's brief, revise, decline.
- Both surfaces **hide themselves** when the flag is off (the endpoints 404, and the callers treat
  that as "not available" rather than an error).

**Tests** — 22 in `tests/test_party_quotes.py`. The ones worth knowing about: the bespoke package
appears in neither public listing; the revision cap holds from both sides (second ask, second
revise, and revise-before-asked all 409); an expired quote can't be accepted even before the sweep
runs; an **accepted** quote survives the sweep (money has moved); the superseded slot is retired on
revision/withdrawal/expiry; and the exact headcount band stops anyone booking the bespoke slot
directly at a different size.

---

## 4. Verified behaviour (not just green tests)

Full flow driven against the running API inside a rolled-back transaction (no dev-DB writes):

```
1. brief          201 submitted
2. quote          201 total 70000  deposit 21000
3. revision ask   200 revision_requested
4. revised        200 total 63000  revision_count 1
5. 2nd round      409                    <- ADR-0009 fence holds
6. accept         200 pending_deposit  deposit 18900  client_secret present
7. deposit paid   200 confirmed            <- the unchanged instant-book rails
8. leak check     bespoke package public? False
9. emails         enquiry / quote / revision ask / revised quote / accepted
```

---

## 5. Invariants

- **INV-1** — accept goes through the unchanged `book_slot`; capacity-1 stays the DB's guarantee.
  The sweep only ever cancels an `available` slot — once a booking exists the slot belongs to the
  money path and is left alone.
- **INV-2** — no new money movement; the deposit is the existing `payments` path.
- **INV-3** — the brief has **no field** for a child's name or DOB (kid count + age band only), and
  a test asserts the schema can't grow one silently. Notes are the one free-text risk: the UI hint
  says "please don't include kids' names".
- **INV-6** — quoted prices are GST-inclusive, like every other displayed party price.
- **INV-11** — quote expiry is a bounded, audited config setting.
- **Non-goal fence (EXT-1 §10)** — one revision, one message each way. Not a chat, and the DB
  CHECK means it can't quietly become one.

---

## 6. Known gaps / next steps

- **Not pushed, not merged.** The branch also has no PR yet.
- **Adversarial review.** No subagent review was run (out of scope this session by instruction).
  This diff writes no money code, which is why I was comfortable; a fresh skeptical pass on the
  *access control* (who can read a brief, who can quote) would still be worth it before merge.
- **The flag stays OFF until real email lands.** A brief nobody is told about is a dead end, so
  turning `party_quotes` on before SMTP credentials exist would be worse than leaving it dark.
- **Not built, deliberately:** quote history (revisions replace in place, capped at one),
  provider-side quote analytics, and any "compare quotes from several providers" view — a brief
  goes to one provider, per PRD §9.
- **Nice-to-have:** the parent's enquiry form picks the provider from a flat list of everyone with
  a party package. Once there are more than a handful of providers that wants to become a search.
- Still open from the earlier session: SMTP credentials, Stripe test keys (prod is on the
  `FakeGateway`), SSR prefetch serialization, deploy hardening.

---

## 7. Where to look

- Plan + the money-seam rationale: `docs/PLANS/milestone-C-request-to-quote.md`; ADR-0009.
- Backend: `apps/api/src/juggle/modules/parties/core/{quotes,models,schemas}.py`,
  `parties/ui/quote_routes.py`, migration `61452b91bbf6`, `scheduler/core/service.py`.
- Frontend: `apps/web/src/pages/PartyQuotesPage.vue`,
  `apps/web/src/pages/provider/ProviderOrgPage.vue` (Party enquiries section),
  `apps/web/src/lib/{api,types}.ts`.
- Guides: `GUIDE-user.md` §6 (asking for a quote), `GUIDE-provider.md` §4b (quoting).
