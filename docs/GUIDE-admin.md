# Admin Guide — kidspots.store

**Who this is for:** kidspots operators with an admin account. The admin console is the control
room for the marketplace: approving providers, verifying compliance, running bookings and payout
operations, tuning runtime configuration, managing feature flags, handling privacy requests, and
providing support via impersonation.

> **Access:** admin features live under **kidspots.store/admin** and are only visible to accounts
> with the admin flag. There is **no admin sign-up** by design — an existing admin (or an operator
> with database access) grants admin rights. See [Appendix A](#appendix-a--bootstrapping-the-first-admin).

**Admin navigation:** Approvals · Payouts · Reviews · Configuration · Feature flags · Audit log ·
Funnel · Users · Operations · Impersonation. (Opening **/admin** lands you on **Approvals**.)

---

## 1. Provider approvals & verification

**Nav → Approvals**

New providers self-register and start as **Pending**. This page is where you review and gate them.

- **Tabs:** Pending / Approved / Suspended. Each row shows the org name, status, and **reliability
  score** (as a percentage).
- **Approve** — clears a provider to operate with full trust. (Note: a provider can technically
  publish while Pending; approval is your trust signal and gates verification.)
- **Suspend** — stops a provider from **publishing** new listings. Use for policy breaches or risk.
- **Review dialog** — opens the org's compliance bundle:
  - **WWCC** (Working with Children Checks) — **verify** or **reject** each.
  - **Public liability insurance** documents — **verify** or **reject** each.
  - Approve the provider from within the dialog once satisfied.

Verifying WWCC/insurance is what earns providers their **verification badges** (alongside a present
ABN). Expiry is tracked automatically — lapsed documents stop counting.

### Listing moderation
Individual listings can be **rejected** (unpublished) for policy reasons. The reasons include
**recurring enrolment** (the key fence — term-enrolment classes disguised as one-offs are not
allowed), **safety concern**, **misleading content**, **policy violation**, or **other**.

> This action is available via the API but does not yet have its own admin page — flag it if you
> need it surfaced in the UI. Review moderation (below) does have a dedicated page.

---

## 2. Review moderation

**Nav → Reviews**

Parent reviews are queued for moderation before they go public.
- The **moderation queue** shows pending reviews.
- **Approve** to publish, or **reject** with a reason.
- Your moderator identity is recorded on the decision.

Reviews can only be submitted by parents who **actually attended** a session, but moderation is
your safety net for abuse, PII, or off-topic content.

---

## 3. Users & privacy

**Nav → Users**

Search users by email or name, then per user:
- **Booking history** — look up a user's bookings to help with support (PRD §10.2).
- **Suspend / reinstate** — block an account (fraud, abuse, chargebacks) without touching any data.
  The effect is immediate and total: they are signed out of every device, an already-issued token
  stops working on its next request, and they can neither refresh nor sign in again. Reinstating
  restores the account exactly as it was — they just sign in fresh. You are asked for a reason, and
  it is written to the audit trail.
- **Delete account (APP)** — action an Australian Privacy Principles data-erasure request. This
  permanently removes the account and personal data.
- **Merge duplicates** — fold a duplicate account into the primary one (the duplicate is
  deactivated, the primary kept).

> **Suspension vs deletion:** suspension is a reversible access decision; deletion is an
> irreversible privacy action. A data-deleted account can no longer be suspended or reinstated
> (the API returns 409) — there is nothing left to restore.

> **Guardrail:** admin accounts are **protected** — they cannot be suspended, data-deleted, or
> merged, and you cannot suspend yourself. The UI hides those controls and the API refuses (409).
> Admin access is granted and revoked at the database level by design (see Appendix A).

---

## 4. Bookings ops & refunds

Admins can issue a **refund** on any payment through the payment gateway (with a reason), used for
support resolutions and disputes.

> **Note:** the refund capability exists in the system but is **not currently wired to a button**
> in the admin UI — it's available at the API level. Everyday refunds happen automatically when a
> provider cancels a session (full refund + payout clawback). Flag this if you need a manual-refund
> screen.

User booking history for support lookups is on the **Users** page (above).

---

## 5. Payouts (provider earnings ops)

**Nav → Payouts**

Provider earnings become **due a few days after** each session, then are released to the provider's
Stripe account. This page controls that.

- **Filter** payouts by status: scheduled / paid / held / reversed.
- **Run due payouts** — release everything currently due (returns a count and total released).
  This is a **deliberate, separate action** from the general maintenance tick.
- **Hold** a payout — freeze it (e.g. under investigation).
- **Release** a held payout — clear the hold.

> Payouts to a provider whose Stripe account isn't **payouts-enabled** are automatically skipped
> and stay scheduled for a later run — they never go to a dead end.

---

## 6. Runtime configuration

**Nav → Configuration**

Operational levers live in the database and take effect **immediately, with no deploy**. Every
change is **validated against min/max bounds, versioned, and audited** (with your identity and an
optional note). Each setting shows its effective value, default, allowed range, and description,
plus a **version history**.

Key settings you can tune include:

| Setting | What it controls |
| --- | --- |
| **Platform fee rate** | Commission % taken from bookings (default 10%) |
| **GST rate** | GST applied to the commission |
| **Seat-hold TTL** | How long a browsing seat-hold lasts before it expires |
| **Checkout window** | How long a started checkout has to complete |
| **Reliability penalty** | How much a cancellation dents a provider's reliability score |
| **Search default radius** | Default km radius for location search |
| **Payout delay days** | Days after a session before earnings become due |
| **Impersonation TTL** | How long a support impersonation session lasts |
| **Waitlist claim window** | How long a freed-seat offer stays claimable |
| **Max active holds per guardian** | Anti-hoarding cap on concurrent seat holds |
| **Party-planner levers** | Deposit %, balance timing, voting/RSVP options, purge timers |

> **Never hard-code these.** They belong here precisely so you can adjust them without an engineer.
> Changes are audited — you can always see who changed what, when, and to what.

---

## 7. Feature flags

**Nav → Feature flags**

Turn features on/off, roll them out by **percentage**, or **target** specific users or orgs. Every
flag change records who made it.

Two flags that are commonly **off in production**:
- **`party_planner`** — the vote-to-book party planner. Depends on a real email gateway being
  wired; keep it off until email is live (its guest emails otherwise run through a stub).
- **`planner`** — the AI holiday-itinerary planner.

Turning a flag on here is what makes those surfaces appear for parents.

---

## 8. Impersonation (support: view-as / act-as)

**Nav → Impersonation**

The safe, audited way to see and fix things from a user's perspective.

**Starting a session:**
1. Search the user by email.
2. Choose a **mode**:
   - **View-as** — **strictly read-only**. You see exactly what they see; any attempt to change
     something is blocked.
   - **Act-as** — you can perform actions on their behalf; **every action is audit-logged** with
     you as the true actor.
3. Optionally record a **reason**.
4. **Start**, then **Enter session** — the app switches into the impersonated view.

**While impersonating:** a persistent **banner** is always shown (labelled "view only" or "can
act") with an **Exit session** button. Exiting restores your own admin session.

**Guardrails (non-negotiable):**
- You **cannot** impersonate yourself or another admin.
- Sessions are **time-boxed** (the impersonation TTL from Configuration) and end automatically on
  expiry.
- The impersonation token **cannot be refreshed** — it fails closed rather than silently extending.
- **Start and end** are both written to the **audit log**, and under act-as **every action** is
  recorded with you as the true actor and the user as the impersonated party.
- Sensitive/admin actions are blocked even under act-as — impersonation can never escalate to admin
  powers.

The page also lists currently **active** sessions with an **End** action.

---

## 9. Audit log

**Nav → Audit log**

Every consequential action across the platform, newest first — approvals/suspensions,
verifications, refunds, payout holds/releases, config and flag changes, and impersonation
start/end and act-as mutations. You can filter by **action** and **entity type**.

Crucially, **impersonated actions record the true (admin) actor**, so there's never an anonymous or
invisible action. This is your accountability trail.

---

## 10. Funnel (product analytics)

**Nav → Funnel**

A platform-wide **product funnel** over a chosen window (default 30 days) built from the product
event taxonomy — how users move from discovery through to booking. Adjust the day range to zoom in
or out.

(Per-provider analytics — fill-rate, revenue, family mix — belong to each provider on their own org
page and are not part of the admin console.)

---

## 11. Operations (maintenance)

**Nav → Operations**

The platform runs a periodic **maintenance tick** that:
- reclaims expired seat holds,
- makes and expires **waitlist offers**,
- sends booking **reminders** and "what to bring" notices,
- tracks **compliance-document expiry**,
- prunes expired auth/throttle rows.

Normally a background **worker** runs this automatically (every few minutes). This page has a **Run
maintenance now** button to trigger a tick on demand — handy for testing or after a config change.

> **Payout release is separate** — it's the **Run due payouts** action on the **Payouts** page, not
> part of this tick.

---

## Appendix A — Bootstrapping the first admin

There is no admin sign-up endpoint by design. To create the first admin (or grant admin to an
account):

1. Have the person **sign up a normal account** through the site.
2. On the server, flip the flag directly in the database:

   ```bash
   docker compose -f docker-compose.prod.yml exec db \
     psql -U juggle -d juggle -c \
     "UPDATE user_account SET is_admin = true WHERE email = 'them@example.com';"
   ```
3. They **log out and back in** to pick up admin access.

Admin rights are read from the account on every request, so the change takes effect on next login.
See `docs/DEPLOY-kidspots.md §7` for the deployment context.

---

## Quick reference — guardrails you rely on

- **Approvals:** Suspend blocks publishing; verification badges require *verified* WWCC/insurance +
  ABN and lapse on expiry.
- **Config:** every change is bounded, versioned, and audited — no deploy needed.
- **Impersonation:** view-as is read-only, act-as is fully audited, never self/admin, time-boxed,
  token can't refresh, can't escalate.
- **Users:** admin accounts are protected from suspension, deletion and merge; suspension is
  reversible and immediate everywhere, deletion is not reversible at all.
- **Payouts:** skipped safely when a provider isn't payouts-enabled; hold/release under your control.
- **Everything consequential is in the Audit log** with the true actor.

---

*Related docs: `docs/GUIDE-provider.md` (what providers see), `docs/GUIDE-user.md` (what parents
see), `docs/DEPLOY-kidspots.md` (running the production stack), `docs/juggle-prd.md` (product spec /
source of truth).*
