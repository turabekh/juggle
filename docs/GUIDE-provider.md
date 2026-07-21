# Provider Guide — kidspots.store

**Who this is for:** activity providers — the businesses and organisers who list kids'
activities on kidspots, manage capacity and rosters, and get paid.

The provider tools are **free**. You self-serve everything: create your organisation, list
sessions, manage bookings and rosters, message families, and receive payouts. This guide
follows the natural lifecycle from sign-up to getting paid.

> **Where the tools live:** after signing in, switch to the provider console at
> **kidspots.store/provider**. The left drawer has your **Dashboard** and a list of your
> **Organisations**. Almost everything happens on two pages: your **Organisation page**
> (compliance, venues, programs, earnings, insights, reviews, Q&A) and a **Program page**
> (sessions, rosters, messaging, cancellations).

---

## 1. Getting set up

### Create your organisation
1. In the provider console, choose **New organisation**.
2. Enter your organisation's name.
3. You become the **owner**. Your org starts with status **Pending** (awaiting admin approval).

> **You can start building immediately while Pending** — set up venues, create programs, and
> even publish listings. Admin **approval** is about trust and verification; the only thing that
> hard-blocks publishing is being **Suspended**.

### Add team members
On the org page you can add other kidspots users as **members** so they can help manage the org.
- **Only an owner can add members.**
- The person must already have a kidspots account.

### Compliance & verification
Buyers trust verified providers. On the **Compliance & verification** section of your org page:

- **ABN** — enter your Australian Business Number.
- **Working with Children Checks (WWCC)** — add each relevant staff member's WWCC (name, number,
  and **expiry date**).
- **Public liability insurance** — add your certificate reference and its expiry.

The admin team reviews and **verifies** these. Once verified, your org earns **verification
badges** (ABN present, WWCC verified, insurance verified). Expiry is tracked for you — a lapsed
document shows a red warning and stops counting toward your badges (amber warns you ~30 days
out), so keep them current.

> **Note on rosters & WWCC:** the platform captures WWCC records for verification badges today.
> Automatic blocking of un-checked staff from a session roster is **not yet a feature** — for
> now, assigning appropriately-checked staff to sessions remains your responsibility.

### Set up payouts (Stripe)
To receive money you connect a **Stripe Express** account:
1. In the **Earnings** section of your org page, choose **Set up payouts / Start onboarding**.
2. You're redirected to Stripe's secure hosted onboarding to enter your business and bank
   details.
3. On return, we re-check your account and show your status: **onboarded**, **charges enabled**,
   and **payouts enabled**.

> **Payout gating:** we only release a payout once your Stripe account has **payouts enabled**.
> Until then, earnings stay **scheduled** and are released on a later run — nothing is lost.

---

## 2. Creating listings & sessions

### Venues
Add each **venue** where you run activities (name, address, suburb, postcode, and location).
Sessions must use a venue that belongs to your org.

### Programs (listings)
Create a **program** — the listing shell: title, category, and description. A program groups the
individual dated sessions parents actually book.

### Publish
A program isn't visible to parents until you **Publish** it. Publishing is blocked only if your
org is **Suspended**.

### Sessions — the bookable dates
On a **Program page**, add the sessions parents book. Each session has:
- **Venue**, **start/end** date-time,
- **Capacity** (how many seats),
- **Price**,
- **Age range** (min–max),
- **Day type** (e.g. half-day / full-day),
- Drop-off and **what-to-bring** notes.

Three ways to create sessions quickly:
- **Add session** — one at a time.
- **Add several** (bulk) — generate many sessions across a date range in one go (e.g. every
  weekday for two weeks), with a preview.
- **Duplicate to new dates** — re-list an existing program's whole run into a new cycle, shifted
  forward by a number of days. Great for the next school holidays.

> **No recurring enrolment.** kidspots is for one-off and drop-in sessions and holiday programs.
> Ongoing term-enrolment classes (with make-ups, term schedules, recurring billing) are **not**
> allowed and are rejected at moderation. That ongoing relationship stays entirely with you.

---

## 3. Capacity, rosters & attendance

### Capacity
Capacity is set **per session** when you create it. The platform enforces it strictly —
**overselling is impossible**, even under simultaneous bookings.

### Roster
On a Program page, open a session's **Roster** to see every booked child with the details you
need on the day: **first name, age, medical/allergy notes, and emergency contact**.

### Attendance check-in
On the roster, tick each child as **present** as they arrive. A running "**X of N checked in**"
count keeps you oriented.

### Export
Download the roster as a **CSV** for offline use or your own records.

---

## 4. Bookings, cancellations & refunds

### Seeing bookings
Your org's **orders** (for invoicing) are listed on the org page; per-session, the roster shows
who's coming.

### Cancelling a session
If you must cancel a session, use **Cancel** on the Program page:
- **Only an owner can cancel.**
- Every family booked on that session is **automatically refunded** for that session.
- All seats are released and the session is marked cancelled.
- In a multi-session cart, only the cancelled session is refunded — the family's other sessions
  stand.

> **This affects your reliability score.** Each provider carries a reliability score; cancelling
> sessions dents it. The platform also claws back the corresponding payout automatically (see
> below), so cancellations are genuinely cost-neutral to families and to the platform.

---

## 5. Getting paid

### How the money splits
For each booking:
- Parents pay the **GST-inclusive** price.
- The platform takes a **commission** (default **10%**, calculated on the ex-GST amount) **plus
  GST on that commission**, which the platform remits to the ATO.
- **Your net = gross − commission − commission GST.**

(The exact commission and GST rates are set by the platform and can be adjusted by admins.)

### Payouts
Earnings for a session become **due a few days after** it runs, then are released to your Stripe
account. On the **Earnings** section you'll see:
- your Stripe payout **status**,
- a list of **payouts** with their status (scheduled / paid / held / reversed),
- an **upcoming** total of what's scheduled.

If a booking is refunded (e.g. you cancel), the matching amount is **clawed back** — deducted
from a not-yet-paid payout, or reversed from an already-paid one — so the books always balance.

### Tax invoices
In the **Tax invoices** section, each order can generate a **commission tax invoice**: the
platform is the supplier, you're the recipient, itemised with per-session **Gross / Commission /
GST / Net** lines and totals. Use these for your BAS/accounting.

---

## 6. Engaging families

### Broadcast messages
From a Program page, **Message** the families with a confirmed booking on a session. Pick a
template — **What to bring**, **Friendly reminder**, **An update**, or **Custom** — set a subject
and body, and send. You'll see a "sent to N families" confirmation. Past broadcasts for a session
are listed for reference. (Only families with a confirmed booking are contacted; if there are
none, there's no one to message.)

### Reviews
The **Reviews** section shows your average rating and each review. You can post a **public reply**
to any **published** review — a good way to thank families or address feedback. (Reviews come only
from parents who actually attended, and are moderated before publishing.)

### Q&A
Parents can ask questions on your listings. The **Questions** section flags how many are waiting.
**Answer** them — your reply is published on the listing, so a good answer helps every future
parent. Only your org's members can answer your listings' questions.

### Waitlists
When a session sells out, parents can join its **waitlist**. On the Program page a full session
shows its queue ("X offered · Y waiting"). Freed seats are offered to the next in line
automatically — you don't have to manage the queue by hand.

---

## 7. Insights (analytics)

The **Insights** section of your org page gives you the numbers that matter:
- **Seats filled** — your fill-rate (booked vs capacity),
- **Bookings revenue**,
- **Families** — the mix of returning vs new,
- a per-program breakdown of fill-rate and revenue.

Use it to see which programs are working and where you have spare capacity to promote.

---

## Quick reference — the rules that matter

- **Pending is fine to build in;** only **Suspended** blocks publishing.
- **Owners** add members and cancel sessions; other members manage day-to-day.
- **Overselling is impossible** — capacity is enforced by the platform.
- **Provider-cancel ⇒ automatic full refund** for that session + payout clawback + reliability
  hit.
- **Commission 10% + GST**, deducted before your net payout.
- **Payouts need Stripe "payouts enabled"** — otherwise earnings wait, safely, for a later run.
- **Verification badges** need *verified* WWCC/insurance + an ABN, and lapse when a document
  expires — keep them current.
- **No recurring/term enrolment** — one-off, drop-in, and holiday sessions only.
- **Child data** on rosters is first name + DOB/age + medical + emergency contact only — treat it
  as confidential and don't export it beyond what you need for the day.

---

*Something looks stuck (e.g. an org not approved, a document not verified)? Contact the kidspots
admin team — they handle approvals, verification, and payout operations. See the Admin Guide.*
