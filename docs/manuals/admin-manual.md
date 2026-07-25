# Juggle — Administrator Manual

**Who this is for:** whoever operates the Juggle platform — approving providers, handling
refunds and payouts, tuning runtime settings, and supporting families and providers.

**What admin access means.** Admin is the most powerful role in the system: you can move
money, see any user's bookings, act as another person, and change settings that affect
every booking made from that moment on. Almost everything you do here is written to an
append-only audit log with your name on it. That's deliberate.

---

## Contents

1. [Getting admin access](#1-getting-admin-access)
2. [The console at a glance](#2-the-console-at-a-glance)
3. [Provider approvals and verification](#3-provider-approvals-and-verification)
4. [Listing moderation](#4-listing-moderation)
5. [Review moderation](#5-review-moderation)
6. [Users and privacy](#6-users-and-privacy)
7. [Bookings, refunds and disputes](#7-bookings-refunds-and-disputes)
8. [Payouts](#8-payouts)
9. [Runtime configuration](#9-runtime-configuration)
10. [Feature flags](#10-feature-flags)
11. [Impersonation — supporting a user](#11-impersonation--supporting-a-user)
12. [Audit log](#12-audit-log)
13. [Funnel](#13-funnel)
14. [Operations — the maintenance worker](#14-operations--the-maintenance-worker)
15. [Runbook — common situations](#15-runbook--common-situations)
16. [Guardrails you can rely on](#16-guardrails-you-can-rely-on)

---

## 1. Getting admin access

There is **no admin-creation screen, by design**. Admin is granted at the database level:

```sql
UPDATE user_account SET is_admin = true WHERE email = 'you@example.com';
```

Sign out and back in afterwards — the admin claim is written into your session at login.

Consequences worth understanding:

- Admin accounts **cannot be suspended or deleted** from the console (§6). Revoking admin is
  a database operation too. This stops the console becoming an admin-lockout weapon with no
  way back in.
- Impersonation tokens can **never** grant admin (§11), so no support session can escalate.

---

## 2. The console at a glance

`/admin`, ten sections:

| Section | What it's for |
| --- | --- |
| **Approvals** | Approve, suspend and verify providers |
| **Payouts** | Provider earnings: run, hold, release |
| **Reviews** | Moderate parent reviews |
| **Configuration** | Runtime settings — fees, TTLs, party rules |
| **Feature flags** | Turn features on/off, roll out gradually |
| **Audit log** | Everything consequential, with the true actor |
| **Funnel** | Product analytics — search → book |
| **Users** | Lookup, suspend, delete, merge |
| **Operations** | Run the maintenance tick |
| **Impersonation** | View-as / act-as support sessions |

On a phone the console nav collapses behind the hamburger in the header; the wide tables
scroll sideways within their card.

---

## 3. Provider approvals and verification

**Approvals**, tabbed by **Pending / Approved / Suspended**.

### Approving

A provider signs up and builds out venues, programs and sessions immediately — but
**nothing is publicly bookable until you approve the organisation**. Approve when you're
satisfied they're real and compliant.

**Suspend** an approved provider to stop them publishing. Existing bookings are not
touched by suspension; deal with those separately (§7) if the situation calls for it.

### Verification

Per organisation you verify:

- **WWCC** — a Working with Children Check per staff member, with an expiry date.
- **Public liability insurance** — a certificate, with an expiry date.
- **ABN** — the provider enters it; you confirm it.

Two things happen automatically:

- **Verification badges** on the provider's public listings. These are **four independent
  signals** — approved, ABN on file, WWCC verified, insurance verified — not a single
  combined badge. "WWCC verified" means the organisation has **at least one** verified WWCC
  record on file; it does not mean every staff member has been checked.
- **Expiry tracking** — a check or certificate that passes its expiry date is marked expired
  by the maintenance tick, and the corresponding badge lapses with it. You don't have to
  diarise renewals.

> **What the WWCC signal does and does not mean.** Juggle collects and verifies WWCC records
> per staff member and tracks their expiry, but **it does not currently assign staff to
> sessions** — the session roster is the list of *children* attending, not of staff working.
> So there is no automated block on an unchecked adult working a session: deciding who staffs
> a session remains the **provider's** legal responsibility. Treat the badge as "this
> provider has produced a valid check", not as a per-session guarantee.
>
> *(A staffing gate is a stated design invariant for when staff assignment is built. Until
> then, don't describe it to providers or families as if it already exists.)*

---

## 4. Listing moderation

From the Approvals area you can **reject a listing**, which unpublishes it with a reason
code and an audit entry.

The reason code that matters most is **`recurring_enrolment`**. Juggle sells one-off and
drop-in sessions. Term-long enrolments, ongoing weekly classes and anything that's really a
subscription dressed as a one-off are **out of scope and rejected here** — the ongoing
relationship belongs to the provider, not the platform. If you see a listing that's really
"Term 3, 10 weeks, pay upfront", that's this button.

---

## 5. Review moderation

**Reviews** holds the moderation queue. Only families with a **verified booking** can review
at all, so you're not fighting drive-by spam.

Moderate anything that names a child (the system screens for this too), identifies a family,
or is abusive. Providers may post one reply per review; those are moderated on the same
terms.

---

## 6. Users and privacy

**Users** — search by email or name, then per user:

### Booking history
Look up any user's bookings to answer a support question without needing them to screenshot
anything.

### Suspend / reinstate
Blocks an account: they **cannot sign in, cannot refresh an existing session, and every open
session dies on its next request** — sign-out is immediate and total, everywhere. You're
asked for a reason, which goes into the audit log.

Suspension is a **reversible access decision** — it touches no data. Reinstating restores
the account exactly as it was; the user simply signs in again (their old sessions were
revoked, so they need their credentials, not a stale tab).

Use it for fraud, chargebacks, and abuse.

### Delete account (APP)
Actions an Australian Privacy Principles erasure request. Permanently strips the guardian's
personal data **and their children's**. Bookings and payment rows survive as financial
records but carry no personal information.

**This is irreversible.** A deleted account can no longer be suspended or reinstated — the
console returns a conflict if you try, because there's nothing left to restore.

### Merge duplicates
Folds a duplicate account into the primary one — kids, bookings and waitlist entries move
across, and the duplicate is deactivated.

> **Guardrails:** admin accounts are protected from suspension, deletion and merge, and you
> cannot suspend yourself. The UI hides those controls and the API refuses with a 409.

---

## 7. Bookings, refunds and disputes

You can **refund any payment** with a reason. Use it for support resolutions, disputes and
goodwill.

Two automatic behaviours you should know so you don't duplicate them by hand:

- **A provider cancelling a session refunds every booking on it automatically**, and claws
  back the provider's payout for it. You don't need to issue those refunds.
- **A seat lost during payment** (two families paying for the last seat simultaneously)
  auto-refunds the family that missed out and emails them an explanation.

**Partial refunds** happen naturally when a provider cancels one session out of a
multi-session order — only that session is refunded, the rest of the order stands.

Every refund reverses the corresponding provider payout, whether that payout is still
scheduled (decremented) or already paid (reversed at the payment provider). You cannot
refund a family and accidentally leave the provider holding the money.

---

## 8. Payouts

**Payouts** lists provider earnings by status: **scheduled**, **paid**, **held**,
**reversed**.

### How the money splits

For each booking: the family pays a GST-inclusive price. Juggle takes a **commission**
(10% by default), plus **GST on that commission**. The provider's net is
`line − commission − commission GST`, rounded per session.

### Running payouts

Payouts become due a set number of days after the session runs (**2 by default**). **Run
payouts** releases everything currently due, across all providers.

- A provider who hasn't finished payment onboarding is **skipped safely** — their money
  stays scheduled until they're ready, rather than failing.
- **Hold** a payout to stop it releasing (a dispute, a suspicious provider). **Release**
  it to put it back in the queue.
- The run is idempotent and safe to repeat.

### Tax invoices

Providers can download a GST tax invoice per order, itemising Juggle's commission and the
GST on it. The supplier identity on those invoices comes from deployment configuration
(legal name and ABN), not from anything you set in the console.

---

## 9. Runtime configuration

**Configuration** — operational levers that take effect **immediately, with no deploy**.
Every setting is typed, bounded, versioned and audit-logged, and every change records who
made it. Each row has a history you can inspect.

Changes apply to **future** activity. Changing the commission rate does not retrospectively
alter bookings already taken — a refund always claws back exactly what was accrued at the
time.

### The full list

**Money**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `platform_fee_rate` | 0.10 | 0–0.20 | Marketplace commission rate |
| `gst_rate` | 0.10 | 0–0.20 | GST applied to the commission |
| `payout_delay_days` | 2 | 0–30 | Days after a session before payout is due |

**Inventory and checkout**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `seat_hold_ttl_seconds` | 900 | 60–3600 | How long a browsing hold lasts |
| `checkout_window_seconds` | 1200 | 300–3600 | How long a checkout may sit unpaid before the seats are released |
| `max_active_holds_per_guardian` | 8 | 1–50 | Anti-hoarding cap on concurrent holds |
| `waitlist_claim_window_minutes` | 240 | 15–2880 | How long a waitlist offer stays claimable |

**Discovery and trust**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `search_default_radius_km` | 25.0 | 1–200 | Default search radius |
| `reliability_cancellation_penalty` | 0.10 | 0–1.0 | Reliability-score hit per provider cancellation |

**Support**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `impersonation_ttl_minutes` | 30 | 5–480 | Support session lifetime |

**Parties — deposits and balances**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `party_deposit_pct` | 30 | 10–100 | Deposit percentage at booking |
| `party_balance_offset_days` | 7 | 0–30 | Days before the party to start charging the balance |
| `party_balance_cutoff_hours` | 72 | 0–336 | Hours before the party after which an unpaid balance auto-cancels |
| `party_balance_retry_interval_hours` | 48 | 1–336 | Minimum gap between balance attempts |
| `party_balance_max_attempts` | 3 | 1–10 | Attempts before auto-cancel |

**Parties — quotes**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `party_quote_expiry_hours` | 72 | 12–336 | How long a quote stays acceptable |

**Party votes (planner)**

| Setting | Default | Range | What it does |
| --- | --- | --- | --- |
| `party_planner_max_options` | 4 | 2–4 | Options a plan may offer |
| `party_planner_min_deadline_gap_hours` | 24 | 1–168 | Minimum gap between the deadline and the earliest option |
| `party_planner_low_rsvp_threshold` | 5 | 0–100 | RSVP count below which a nudge fires at T-24h |
| `party_planner_extend_hours` | 48 | 1–168 | Length of a one-tap deadline extension |
| `party_planner_purge_days` | 30 | 1–365 | Days after the event before guest PII is purged |
| `party_planner_rsvp_rate_per_hour` | 20 | 1–1000 | Per-IP/token RSVP+vote rate limit |
| `party_planner_custom_option_maxlen` | 80 | 10–200 | Max length of a custom option or nickname |
| `party_planner_page_title_maxlen` | 60 | 10–120 | Max length of a party page title |
| `party_planner_page_message_maxlen` | 280 | 0–1000 | Max length of a party page welcome message |

> **Settings you should think twice about.** Lowering `seat_hold_ttl_seconds` frustrates
> families mid-decision; raising it lets seats sit idle and depresses real availability.
> `platform_fee_rate` and `gst_rate` change what providers earn on every subsequent
> booking — tell them before you touch either.

---

## 10. Feature flags

**Feature flags** turns features on and off without a deploy, with optional percentage
rollout and targeting.

Flags currently in use:

| Flag | Controls |
| --- | --- |
| `planner` | The AI holiday planner |
| `party_planner` | Party votes: invites, voting, guest pages |
| `party_quotes` | Bespoke party enquiries and quotes |

When a flag is off, its endpoints return **404** and the matching UI hides itself entirely —
users don't see a broken or teasing surface.

> **Both party features are email-driven end to end.** An invitation or quote that nobody is
> told about is a dead end, so keep `party_planner` and `party_quotes` **off until real
> email delivery is configured** on the deployment.

---

## 11. Impersonation — supporting a user

**Impersonation** lets you see exactly what a user sees, or act on their behalf.

Two modes:

- **View-as** — strictly read-only. Any attempt to change something is refused.
- **Act-as** — can perform actions as that user, for when you need to fix something for
  them.

Start a session by finding the user, choosing the mode, and giving a reason. Then **enter**
the session; **end** it when you're done.

**What is true of every impersonation session, always:**

- It is **time-boxed** (30 minutes by default, configurable).
- The impersonated UI shows a **banner** the whole time — it is never invisible.
- Every action carries **your** identity as the true actor into the audit log, alongside the
  user you were acting as.
- The token **cannot escalate to admin** and **cannot be refreshed** into a longer session.
- Ending the session revokes it immediately.
- You can impersonate a **suspended or deleted** account — that's deliberate, because those
  are exactly the accounts support needs to look into.

Use the reason field properly. It's what makes an audit entry meaningful six months later.

---

## 12. Audit log

**Audit log** is the append-only record of everything consequential, filterable by entity
type and entity id, always showing the true actor (and the impersonated user, if any).

Recorded actions include:

`admin.org.approve` · `admin.org.suspend` · `admin.listing.reject` · `admin.wwcc.verify` ·
`admin.insurance.verify` · `admin.user.suspend` · `admin.user.reinstate` ·
`admin.accounts_merged` · `identity.account_deleted` · `admin.payment.refund` ·
`admin.payouts.run` · `admin.payout.hold` · `config.set` · `flag.upsert` ·
`impersonation.start` · `impersonation.end` · `review.moderated` · `review.replied` ·
`review.submitted` · `qanda.asked` · `qanda.answered` · `waitlist.joined` ·
`waitlist.offered` · `waitlist.left` · `roster.attendance_marked` · `comms.broadcast_sent`

If you're ever asked "who changed the commission rate, and when", this is the answer.

---

## 13. Funnel

**Funnel** reads the product event taxonomy: search → listing view → hold → checkout →
confirmed booking, over a configurable window.

Use it to spot where families drop out. Note that **no child personal data ever reaches
analytics events** — the funnel counts actions, not people's details.

---

## 14. Operations — the maintenance worker

**Operations** runs the maintenance tick on demand. The same tick normally runs on a
schedule (every 5 minutes in production).

One tick does all of this, idempotently:

- Reclaims **expired seat holds** back into availability
- Sweeps **abandoned checkouts** — releases seats and fails the order past the payment window
- Sweeps **abandoned party deposits**
- Processes **party balances** — the T-7d charge, its retries, and auto-cancel at the cutoff
- Processes the **waitlist** — makes offers, expires unclaimed ones
- Sends **session reminders** (~48h, ~3h) and **what to bring** (~24h)
- Marks **expired compliance** (WWCC, insurance) and lapses the badges
- Resolves **due party votes**, sends nudges, sweeps stale plans, purges expired guest PII
- Expires **due party quotes** and frees the dates behind them
- Prunes expired auth rows (refresh tokens, one-time codes, rate-limit windows)

Running it by hand is safe and useful when you want an effect *now* rather than within five
minutes — for example releasing a waitlist offer immediately after a cancellation.

---

## 15. Runbook — common situations

**"A family says they paid but have no booking."**
Check **Users → their bookings** first. A booking pending for more than a minute or two
usually means the payment didn't settle. Look at the payment, and refund if they were
charged without receiving a seat — though the system normally does that itself.

**"A provider cancelled a session — do I need to refund everyone?"**
No. Refunds and the payout clawback are automatic. Confirm in the audit log, then focus on
communication.

**"A provider is asking where their money is."**
**Payouts** → filter by their organisation. Scheduled means not yet due (2 days after the
session by default). If it's skipped repeatedly, they probably haven't finished payment
onboarding.

**"A parent is abusing a provider in reviews."**
Moderate the review (§5), and suspend the account (§6) if it's a pattern. Suspension is
reversible; deletion is not — don't reach for deletion as a punishment.

**"Someone asked us to delete their data."**
**Users → delete account** (§6). Explain first that it's irreversible and that their
bookings remain as financial records without personal details.

**"A listing looks like a term enrolment."**
Reject it with `recurring_enrolment` (§4).

**"We need to lower the commission for a launch promotion."**
**Configuration → `platform_fee_rate`**. It applies to bookings from that moment on; tell
providers first, and remember the change is in the audit log under your name.

**"A family can't get into their account."**
There's no password-reset email. If their account has a verified phone number they can sign
in by SMS code. Otherwise, impersonate (view-as) to confirm the account state before
deciding what to do.

---

## 16. Guardrails you can rely on

These are enforced by the system, not by anyone remembering:

- **Overselling is impossible.** Seats are protected by database constraints, not just by
  application checks. Two people cannot buy the last seat.
- **Money only moves through the payments module**, and every payment-provider webhook is
  signature-verified and idempotent — a replayed event cannot double-charge or double-refund.
- **Provider cancels ⇒ automatic full refund**, deposits included, with the payout clawed
  back to match.
- **Displayed prices are GST-inclusive**; commission is calculated fee-exclusive and
  invoiced with GST on top.
- **Compliance expiry is tracked for you** — expired WWCC and insurance records lapse the
  provider's verification badges automatically. (Note the limit in §3: Juggle does not
  assign staff to sessions, so this is not a per-session staffing gate.)
- **Availability shown is availability true** — every surface reads live inventory. There is
  no fabricated urgency anywhere in the product, and adding some would be a bug.
- **Impersonation is never invisible or anonymous** — banner, audit trail, time-boxed, no
  escalation.
- **Runtime config is governed** — typed, bounded, versioned, audited.
- **Child data is minimal** — first name, DOB, medical notes, emergency contact. No
  surnames, no photos, never in analytics or on a public page.

---

*Related: [`user-manual.md`](user-manual.md) (for parents), `../GUIDE-provider.md` (for
providers), `../DEPLOY.md` and `../DEPLOY-kidspots.md` (running the production stack),
`../juggle-prd.md` (the product specification).*
