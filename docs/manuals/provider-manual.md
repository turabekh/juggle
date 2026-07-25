# Juggle — Provider Manual

**Who this is for:** activity providers, venues and entertainers listing on Juggle
(kidspots.store) — holiday programs, weekend and after-school one-offs, and birthday
parties in and around Perth.

**The short version:** listing is free and self-serve. You keep control of your calendar,
your capacity and your prices. Juggle handles discovery, bookings, payment and refunds, and
pays you out after each session, taking a commission on what you sell.

**How to read it:** §1–§4 gets you live. §5 onward is running the business day to day.
Anything marked *(if enabled)* is switched on deliberately by the Juggle team and may not be
visible yet.

---

## Contents

1. [Getting set up](#1-getting-set-up)
2. [Compliance and verification](#2-compliance-and-verification)
3. [Getting paid — payment setup](#3-getting-paid--payment-setup)
4. [Listing your activities](#4-listing-your-activities)
5. [Sessions — your bookable calendar](#5-sessions--your-bookable-calendar)
6. [Capacity, rosters and attendance](#6-capacity-rosters-and-attendance)
7. [Cancelling a session](#7-cancelling-a-session)
8. [How the money works](#8-how-the-money-works)
9. [Payouts and tax invoices](#9-payouts-and-tax-invoices)
10. [Birthday parties — packages](#10-birthday-parties--packages)
11. [Party enquiries and quotes *(if enabled)*](#11-party-enquiries-and-quotes-if-enabled)
12. [Party votes *(if enabled)*](#12-party-votes-if-enabled)
13. [Talking to families](#13-talking-to-families)
14. [Reviews and questions](#14-reviews-and-questions)
15. [Insights](#15-insights)
16. [Your obligations, and ours](#16-your-obligations-and-ours)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Getting set up

### Create your organisation

Sign up as a normal Juggle user, then open the **provider console** (from the account menu →
**Provider console**) and create an **organisation**. That's your business: name, ABN,
compliance documents, venues, listings and earnings all hang off it.

You can run more than one organisation from a single login — they're listed in the console
sidebar.

### What happens next

You can build everything immediately — venues, programs, sessions, party packages — but
**nothing is publicly bookable until Juggle approves your organisation**. Your console shows
the status:

| Status | What it means |
| --- | --- |
| **pending** | Awaiting approval. Build away; families can't see it yet. |
| **approved** | Live. Published listings are searchable and bookable. |
| **suspended** | You cannot publish. Talk to Juggle. |

Use the pending period to get your compliance documents in (§2) and your calendar built —
approval is much quicker when there's something real to look at.

### Team members

Add colleagues to the organisation so they can manage listings and see rosters. There are
two roles:

| Role | Can do |
| --- | --- |
| **owner** | Everything, including **cancelling a session** |
| **staff** | Manage listings, sessions, packages; see rosters and mark attendance |

The person who creates the organisation is its owner. Staff can run the day to day but
cannot cancel a session out from under booked families — that one deliberately sits with
the owner, because it refunds everyone and dents the organisation's reliability score.

Both roles can see rosters, which contain children's details — add people accordingly.

---

## 2. Compliance and verification

**Provider console → your organisation → Compliance & verification.**

Three things, all verified by Juggle rather than self-declared:

- **ABN** — enter it; Juggle confirms it.
- **Working with Children Checks (WWCC)** — one record per staff member: their name, the
  check number, and its **expiry date**.
- **Public liability insurance** — the certificate reference and its **expiry date**.

### What verification buys you

Verified records show as **trust badges** on your public listings. They're four separate
signals — approved, ABN on file, WWCC verified, insurance verified — and families do notice
them.

### Expiry is tracked automatically

When a check or certificate passes its expiry date, Juggle marks it expired and the matching
badge lapses. You don't get to keep a badge on paperwork that has run out. Your console
warns you as expiry approaches, so keep the dates accurate and renew before they lapse.

> **Important — what the WWCC badge does and does not mean.** Juggle stores and verifies the
> WWCC records you provide and tracks their expiry. It does **not** assign staff to sessions
> — the session roster is the list of *children* attending, not of staff working. **Deciding
> who staffs a session, and making sure they hold a current WWCC, remains entirely your legal
> responsibility.** The badge says "this provider produced a valid check", not "everyone
> working today has been checked."

---

## 3. Getting paid — payment setup

**Provider console → your organisation → payouts setup.**

Juggle pays you through Stripe. You complete a **Stripe onboarding** flow — business
details, and the bank account you want money in. Juggle never sees or stores your bank
details.

Until onboarding is complete and Stripe has enabled payouts on your account:

- You can still list and take bookings.
- Your earnings **accrue** normally and are visible in the console.
- Payout runs **skip you safely** — the money stays scheduled and is released once you're
  ready. Nothing is lost; it just waits.

Finish onboarding before your first session runs and you'll never notice this.

---

## 4. Listing your activities

### Venues

Add a venue for each place you run activities: name, suburb and postcode. Venues carry the
location used for map and radius search, so a family searching "within 10 km of Fremantle"
finds you because of this.

### Programs

A **program** is the thing you offer — "School Holiday Art Camp", "Junior Soccer Clinic".
It carries the title, description, category (sport, art, STEM, drama and others) and the
venue.

### Publish

A program stays a draft until you **publish** it. Publishing is what makes it searchable —
and it requires your organisation to be approved.

> **What must not be listed.** Juggle sells **one-off and drop-in** sessions. Term-long
> enrolments, ongoing weekly classes, and anything that is really a subscription are out of
> scope and are **rejected at moderation**. The ongoing relationship with a family — terms,
> make-up classes, recurring billing — stays yours, off-platform. A listing that's really
> "Term 3, 10 weeks, paid upfront" will be unpublished with a reason.

---

## 5. Sessions — your bookable calendar

A **session** is one bookable date and time on a program. Each carries:

- start and end time
- **capacity** — how many kids you can take
- **price per child** (GST-inclusive — the number the family sees is the number they pay)
- **age range** — enforced at booking, so you don't get a 4-year-old in a 10–12 session
- session type (e.g. full day)
- optional **what to bring**, which is emailed to families about 24 hours before

### Building a calendar quickly

Two shortcuts for the common cases:

- **Duplicate sessions** — copy an existing session to other dates.
- **Bulk sessions** — generate a whole run at once from a date range, the weekdays you run,
  and the time window.

Between them you can put a full school-holiday program up in a couple of minutes instead of
adding thirty sessions by hand.

### Changing a session

Edit details while it's still open. Be careful reducing **capacity** below what's already
booked — you can't un-sell a seat, and the fix is a cancellation (§7), which costs you
money and reputation.

---

## 6. Capacity, rosters and attendance

### Capacity is a hard guarantee

Juggle will not oversell you. Seats are protected at the database level, not by hopeful
application logic: if capacity is 12, at most 12 children can be booked, even if twenty
families check out simultaneously. Browsing families hold a seat for about 15 minutes; if
they don't pay, the seat returns to the pool automatically.

That guarantee is the core of the product. You can trust your roster count.

### The roster

**Session → roster** shows who's coming: each child's **first name**, **age**, the
**medical/allergy notes** the guardian supplied, an **emergency contact**, and the answers
to any **custom questions** you require at checkout.

The standing child record Juggle holds is deliberately minimal — first name, date of birth,
medical notes, emergency contact. **There is no field for a surname or a photo anywhere in
the system**, and that's a design decision rather than an oversight.

> Custom checkout questions are the one place you can widen that. Use them for what you
> genuinely need on the day — a swimming level, a consent, a dietary detail. Please don't
> use them to collect surnames, photos or anything else the platform deliberately doesn't
> hold: it lands in the same roster, and it becomes your responsibility to justify.

### Attendance check-in

Mark each child present or absent on the day, from the roster. It's the quickest record for
ratios and for answering "was my child there?" afterwards.

### Export

Download the roster as **CSV** to print, or to load into whatever you already use on the
day.

---

## 7. Cancelling a session

Cancelling is **owner-only** (§1) — staff members can't do it. If you must cancel, do it
from the session in the console. When you do, Juggle **immediately and automatically**:

- **refunds every family** booked on that session, in full;
- **releases all the seats**;
- **marks the session cancelled**;
- **emails every affected family**;
- **claws back the corresponding payout**, whether it was still scheduled or already paid.

In a multi-session order only the cancelled session is refunded — the family's other
bookings stand.

> **It affects your reliability score.** Every provider carries one, and cancellations dent
> it. Cancelling is genuinely cost-neutral to families and to Juggle — which is exactly why
> the cost lands on you. Cancel when you have to; don't use it to manage over-booking.

**Cancellations by families** are governed by *your* terms, not Juggle's. Families are told
to contact you.

---

## 8. How the money works

A family pays a single GST-inclusive price. From that:

- **Juggle's commission** — 10% by default — calculated on the price excluding our fee;
- **GST on that commission**;
- **the rest is yours**: `price − commission − GST on commission`, rounded per session.

A worked example at the default rate, on a $50.00 seat:

| | |
| --- | --- |
| Family pays | $50.00 |
| Juggle commission (10%) | $5.00 |
| GST on the commission | $0.50 |
| **Your net** | **$44.50** |

Notes that matter:

- **The price you set is the price displayed and charged.** No card surcharge is added to
  the family at the end — card costs are absorbed, not passed on.
- **The commission rate can change** (it's a platform setting). A change applies to bookings
  taken *after* it; it never retrospectively alters money already earned, and a refund
  always claws back exactly what was accrued at the time.

---

## 9. Payouts and tax invoices

### When you get paid

Earnings accrue per session and become due **2 days after the session runs** (the default
delay). Juggle releases due payouts to your Stripe account; from there it's Stripe's normal
schedule to your bank.

Your console shows every payout and its state:

| State | Meaning |
| --- | --- |
| **scheduled** | Accrued, not yet due |
| **paid** | Released to you |
| **held** | Held by Juggle — a dispute or a query; talk to us |
| **reversed** | Clawed back, because the booking was refunded |

If a family is refunded, the matching payout is reversed — decremented if it hadn't been
paid yet, reversed at Stripe if it had. You cannot be left holding money for a booking that
was refunded, and equally, a refund never quietly comes out of an unrelated payout.

### Tax invoices

From the organisation page you can open any order and download a **GST tax invoice** for
Juggle's commission on it — itemising the commission and the GST on it, with Juggle's legal
name and ABN. That's the document your bookkeeper wants for the platform fee.

---

## 10. Birthday parties — packages

**Provider console → your organisation → Party packages.**

A **package** is a party you offer: venue, **per-head price** (GST-inclusive), a
**min/max guest band**, an optional deposit percentage override, and an **outdoor** flag if
a weather clause applies.

Then add **dates**. Each date is **one party** — capacity-1 inventory, so once a family
books it, it's gone. The same anti-oversell guarantee as sessions applies.

### How a party booking pays out

1. The family pays a **deposit** (30% by default) to lock the date.
2. The **balance is charged automatically about 7 days before** the party, to the same card.
3. The family can **adjust their guest count** until about 72 hours before — up charges the
   difference, down refunds it.
4. If the balance can't be charged after several attempts, the booking auto-cancels and you
   are notified — so a silent non-payment doesn't leave you holding a date.

If **you** cancel a party, the family is refunded in full **including the deposit**, always.
An outdoor package's weather clause only ever means **reschedule** — it never means the
family forfeits money.

---

## 11. Party enquiries and quotes *(if enabled)*

For work your packages don't cover — an entertainer at the family's home, a custom setup —
families send a structured **enquiry**, and they appear under **Party enquiries** on your
organisation page.

Each enquiry gives you the date and time, the suburb, how many kids and their age range, an
optional budget, and a short note.

You can:

- **Send a quote** — pick the venue, confirm the time, set the guest count and a per-head
  price, and describe what's included. The form pre-fills from their brief, so usually
  you're only setting a price.
- **Decline** — the family is told, and can approach someone else.

### The one-revision rule

The family may ask for **one** revision ("could you do $45/head?"), and you may send **one**
revised quote in reply. Then it's accept or let it lapse. That limit is deliberate: it keeps
quoting quick and clear instead of turning into a haggling thread. **There is no chat** —
the brief is structured fields, your quote carries one message, their revision request
carries one message. That's the entire conversation.

### Expiry and acceptance

Quotes **expire after 72 hours** by default, which keeps your prices and your calendar
honest. When a family accepts, they pay the same deposit as any party booking and the
balance follows the same schedule — identical money rails, so payouts, refunds and tax
invoices all work exactly as they do for a package booking.

Your quoted price is **private to that family**. It is never listed publicly and never
appears on the marketplace.

> **A quote is a commitment.** The date is held for that family the moment they accept — so
> only quote times you can actually host.

---

## 12. Party votes *(if enabled)*

Families can run a **vote** among their guests to pick between party options — some of which
may be your packages. You don't have to do anything for this to work; if your package wins
the vote, it books through the normal deposit flow and appears like any other party booking.

It's worth knowing it exists, because a family may ask you to hold flexibility while their
guests vote. The vote has a deadline, and slots aren't reserved until someone actually books.

---

## 13. Talking to families

**Broadcasts.** You can send a message to everyone booked into a specific session — a change
of room, a weather note, a reminder to bring boots.

Broadcasts are **template-guarded and scoped to that session**. They are for operational
information about the activity the family has already booked. They are not a marketing
channel, and Juggle does not give you a mailing list.

Juggle separately emails your families, so you don't have to: booking confirmations,
reminders at roughly 48 hours and 3 hours before, and your **what to bring** note about 24
hours before.

---

## 14. Reviews and questions

**Reviews.** Only families with a **confirmed booking on a finished session** can review, so
you're not exposed to drive-by ratings. You may post **one reply** per review — useful for
thanking people, and for putting a calm factual response under an unfair one. Reviews are
moderated by Juggle; anything naming a child or abusive is removed.

**Questions.** Families can ask a public question on your listing. Your answer is published
on the listing, so a good answer saves you the next ten emails about the same thing. Answer
promptly — an unanswered question is visible to everyone considering booking.

---

## 15. Insights

**Insights** on your organisation page shows how you're doing: **fill rate** (how full your
sessions run), **revenue**, and **family mix** (new versus returning).

Fill rate is the number to watch. Consistently low fill usually means price, timing, or a
listing that doesn't say enough — not lack of demand.

---

## 16. Your obligations, and ours

### Yours

- **Staffing and child safety.** You decide who works each session and you are responsible
  for them holding current WWCCs. Juggle stores and verifies the records you give us; we do
  not staff your sessions (§2).
- **Ratios, duty of care, and your own insurance** on the day.
- **Accurate listings** — age ranges, capacity, what's included, what to bring.
- **Honouring bookings.** Families paid on the strength of your calendar.
- **One-off and drop-in only.** No term enrolments or recurring subscriptions (§4).

### Ours

- **We never oversell you.** Capacity is enforced at the database level.
- **The price you set is the price displayed and charged** — GST-inclusive, no surcharge
  bolted on at the end.
- **You are paid for what you deliver**, 2 days after the session, with a GST tax invoice
  for our commission.
- **A refund never quietly comes out of a different payout** — clawbacks are matched exactly
  to the booking refunded.
- **We show real availability.** No invented scarcity, no fake countdowns against your
  listings.
- **Minimal child data** — first name, date of birth, medical notes and an emergency
  contact. Never a surname or a photo.

---

## 17. Troubleshooting

**"My listing isn't showing up in search."**
Check three things in order: is the organisation **approved**; is the program
**published**; does the session still lie in the future with seats left. Search only shows
future sessions from approved providers.

**"A family says the session is full but I have space."**
Seats held by other families mid-checkout count as taken for about 15 minutes. They return
automatically if those families don't pay.

**"I need to reduce capacity below what's booked."**
You can't un-sell a seat. Either honour the bookings or cancel the session (§7), which
refunds everyone and dents your reliability score.

**"Where's my money?"**
Payouts are due 2 days after the session runs. If yours stay **scheduled** past that, the
usual cause is incomplete Stripe onboarding (§3) — runs skip you safely until it's done.
**Held** means Juggle has paused it; contact us.

**"A family wants to cancel."**
That's your policy, not ours. If a refund is warranted, Juggle support can issue it.

**"My verification badge disappeared."**
A WWCC or insurance certificate passed its expiry date and lapsed automatically (§2). Add
the renewed document and it comes back once verified.

**"I want to offer a 10-week term course."**
Not on Juggle — it's out of scope and will be rejected at moderation (§4). List the
individual holiday or one-off sessions here and keep the term relationship direct with the
family.

---

*Related: [`user-manual.md`](user-manual.md) (what families see),
[`admin-manual.md`](admin-manual.md) (the platform operator's view),
`../GUIDE-provider.md` (the short orientation guide).*
