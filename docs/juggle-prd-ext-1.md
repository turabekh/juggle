# PRD Extension 1 — Year-Round Demand & Parent Growth Loops

| | |
|---|---|
| Document | `docs/PRD-EXT-1.md` — extends `docs/PRD.md` v0.1; modifies nothing in the MVP cutline |
| Owner | Turaboy Holmirzaev |
| Date | July 2026 |
| Status | Approved for phased build. **No EXT item may begin before the spring MVP ships**, except G3-lite (pre-launch email capture, already in GTM plan). |

## 1. Purpose

Two gaps in the base PRD, one document:

1. **Seasonality** (base PRD Risk #3): four holiday spikes/year is a fragile revenue curve. This extension adds year-round demand surfaces **without touching loyalty-category enrolments** — the disintermediation trap stays fenced off.
2. **Parent acquisition**: demand-side growth is engineered into the product as loops (bookers recruit bookers), not bought as marketing. Principle: kids' activities are social goods — a booking a friend joins is worth three ads.

Binding constraints inherited from base PRD: variety-seeking categories only; INV-1…11 apply throughout; anything here that conflicts with shipping spring MVP loses.

## 2. Demand calendar (E-series)

### E1 — Pupil-free days [P1]
The unguarded flank: same acute pain as holidays ("random Friday, both parents working"), zero competition, desperate-intent SEO, and demand that recurs ~monthly somewhere in Perth.

- **School-specific reality:** WA pupil-free days vary per school, not statewide. Data model: `school` (name, suburb, geo, sector), `guardian_school` (family's school links, set during onboarding or first booking), `pd_day` (school, date, source, status).
- **Dataset строится three ways:** admin-curated from published school calendars (seed ~top-100 Perth schools), parent-submitted with moderation queue (§10.2 addition), provider-tagged ("we run PD-day programs").
- **Surfaces:** "Pupil-free day coming up at <school> — programs that day near you" (email/push + home banner, T-14d and T-5d); providers can flag sessions as PD-day programs; programmatic SEO pages per date × region.
- **Config (§10.1 delta):** PD dataset management UI, alert lead times.

### E2 — Weekend & one-off sessions [P2]
Saturday pottery, one-day STEM intensives, drop-in circus. Mechanically identical to holiday sessions (same `session` object, date outside holiday calendar) — this is surface work, not model work.

- **Surfaces:** "This weekend" feed (the Discover tab's bookable half), weekend filter in search.
- **Listing policy (guardrail):** one-off/drop-in only; recurring-enrolment classes disguised as one-offs are rejected at moderation. The fence around the loyalty trap is editorial, enforced in §10.2.

### E3 — Long weekends & public holidays [P1, ships with E1]
Pure calendar entries (national/state holidays already known); same alert + surface machinery as E1. Near-zero marginal build.

### E4 — Trial passes & new-family bounties for term classes [P3]
The only safe way to touch the biggest money pool in the category: monetize the **switch moment**, never the relationship.

- **Product:** "Try before you enrol" — book taster sessions at up to N studios in an enrolment window; provider pays a lead fee per **attended trial** ($30–80, config-bounded), optional success bounty on confirmed enrolment (self-reported, audit-sampled).
- **Hand-off is the feature:** after the trial, the relationship (enrolment, billing, scheduling) belongs entirely to the provider. Juggle stores no recurring billing, no term schedules, no make-up classes. Restated as a non-goal below because every future contributor will be tempted.
- **Attribution window:** 30 days trial→enrolment for bounty claims; disputes via §10.2 console.
- **Anti-gaming:** attended-trial fee (check-in-verified) is primary revenue; enrolment bounty is upside, never load-bearing.

## 3. Parent growth loops (G-series)

### G1 — "Book together" share links [P1]
Post-booking share sheet → deep link to the exact session with live seats.

- **Copy defaults privacy-first:** "We've booked Robotics Camp Tue 30 Sep — spots left if you want to join!" Child's first name appears **only** if the sender opts in per share (INV-13). Links never expose rosters or attendee identity.
- **Attribution:** `share_link` carries referrer guardian; booking through it records the edge (feeds metrics + future referral credit).
- **Placement:** confirmation screen, confirmation email, bookings dashboard.

### G2 — Party invites + RSVP [P2, ships with parties vertical]
The acquisition sleeper: one party booking pushes 10–15 parent emails through a Juggle-branded moment.

- Host builds invite from the party booking (theme auto-styled, details prefilled); guests RSVP without accounts; headcount syncs to the booking (respecting the T-72h adjustment rule, base §9); "powered by Juggle" with age-relevant discovery teaser after RSVP.
- **Privacy/consent:** guest emails are the host's data, used solely for that party's transactional comms; any marketing contact requires an explicit separate opt-in at RSVP (Spam Act 2003: transactional vs marketing kept strictly apart). No public guest lists; kids' names visible only within the invite audience.

### G3 — Sold-out capture: waitlists + availability alerts [P1]
Extends base §7.7 waitlists into a subscription asset: "notify me when spots open," "tell me when summer programs drop," per category/suburb/age-band alerts — all capturable **pre-account** (email + kids' ages only). Every disappointment becomes a subscriber. *G3-lite (landing-page email capture with age fields) is already live in the GTM plan and is the only pre-launch EXT item.*

### G4 — Honest scarcity surfaces [P1]
"3 spots left" badges, "80% booked" session states, "filling fast" collections — powered exclusively by the true inventory projection (INV-8) and governed by new INV-12: **only real numbers, ever.** Display thresholds configurable in §10.1. This is the data moat doing the marketing; the moment it's ever caught being fake, the moat drains.

### G5 — Weekly Discover digest [P1 email; Discover tab remains P2]
Age-personalised "what's on for your kids this week/weekend" email: bookable sessions + admin-curated free community events (library, council — generosity is the strategy). Send-time and curation via §10.1; strict opt-in/unsubscribe (Spam Act). The newsletter precedes and funds the eventual Discover tab with an audience.

### G6 — Referral credits [P2]
Give $10 / get $10 booking credit, config-bounded amounts, standard fraud guards (velocity, self-referral block, credit expiry). Amplifier, not igniter — ships only after G1 attribution exists.

## 4. Channel bridges (B-series) [P2 unless noted]

- **B1 — ELC/kindy partner pages:** co-branded landing + QR per centre, partner attribution code, "school-age holiday care for siblings/graduates" framing. Leverages founder's ECEC placement network. Manual partner onboarding; dashboard later.
- **B2 — P&C rev-share tracking:** partner entity + attributed bookings + exportable payout report (manual EFT fine initially).
- **B3 — Employer/FIFO family benefit [P3]:** bulk holiday-program credits as an employee family benefit (mining sector entry via existing network). Note-only until multi-cycle proof.

## 5. New invariants (adopt into CLAUDE.md)

- **INV-12 Scarcity is never fabricated.** Every urgency signal (spots left, % booked, filling fast) derives from the live inventory projection; no synthetic countdowns, no fake "others are viewing," no threshold that displays sooner than truth. If marketing wants urgency, inventory supplies it or it doesn't exist.
- **INV-13 Growth surfaces leak no child PII.** Share links, invites, alerts, digests: no child names in URLs, query params, or analytics events; child first name in share/invite copy only by per-instance sender opt-in; guest/invitee contact data scoped to its transactional purpose with separate marketing consent (Spam Act 2003 discipline).

## 6. Config additions (base §10.1 deltas)

Scarcity display thresholds; referral give/get amounts + expiry; trial lead fee + bounty bounds; PD-day dataset management + alert lead times; digest send-time + curation slots; partner codes.

## 7. Data model deltas

`school, guardian_school, pd_day, share_link, referral, referral_credit, invite, invite_rsvp, alert_subscription, partner, partner_attribution, trial_booking, lead_fee_event`. Module placement (`growth` module vs distributing into catalog/notifications) is an ADR at build time per house rules — recommendation: new `growth` module owning share/referral/invite/alerts + partner attribution; `school`/`pd_day` into `catalog` as geo reference data.

## 8. Success metrics (per feature, conservative)

| Loop | Metric | Healthy |
|---|---|---|
| G1 share links | share→visit→booking conversion | ≥8% of bookings shared; ≥15% of visits book |
| G2 invites | RSVPs per party; RSVP→signup within 60d | ≥10; ≥10% |
| G3 alerts | alert→booking next cycle | ≥20% |
| G5 digest | open rate; digest→session views | ≥45%; ≥10% CTR |
| E1 PD days | bookings per PD date (top-20 schools) | ≥15 by 3rd occurrence |
| E4 trials | attended-trial rate; provider repeat purchase of leads | ≥70%; ≥50% |

North-star addition: **% of new guardians arriving via another guardian's loop** (target ≥25% by mid-2027) — the number that says the flywheel is real.

## 9. Sequencing (relative, not calendar-bound)

1. **Pre-launch (now):** G3-lite email capture only. Nothing else starts.
2. **Post-spring / P1 build window:** G1, G3 full, G4, G5, E1+E3 — alongside base-PRD P1 items (reviews, SMS, refund automation). These are the anti-seasonality bridge to summer.
3. **With parties vertical / P2:** G2 (same release as parties — the invite loop is half the reason to build parties), E2, G6, B1, B2.
4. **P3, after multi-cycle proof:** E4, B3.

## 10. Non-goals (restated, because temptation is structural)

No recurring billing or term-enrolment management, ever, under any feature flag. No purchased contact lists. No fabricated urgency (INV-12). No public rosters or attendee visibility. No chat. No paid placement in the digest while organic trust is being built (revisit ≥2027 with disclosure rules).
