# PRD — "Juggle" (working title)
### Kids' holiday-activities & birthday-party booking marketplace — Australia (Perth beachhead)

| | |
|---|---|
| Version | 0.1 (draft) |
| Owner | Turaboy Holmirzaev |
| Date | July 2026 |
| Status | Pre-gate. Build contingent on August provider-sprint kill criteria passing. |
| Assumed stack | FastAPI + PostgreSQL/PostGIS + Quasar (Vue) PWA, Docker Compose, core/ui split, import-linter module boundaries |

---

## 1. Problem statement

Perth parents assembling school-holiday plans must navigate council PDFs, Facebook posts, TryBooking links, enquiry forms, and per-provider portals (My Family Lounge, Xplor, Kangarootime, direct-debit forms). No surface shows live availability across providers. Providers — mostly micro-businesses — run bookings on spreadsheets and DMs, overselling or under-filling sessions and chasing payments manually.

Demand tailwind: from 5 Jan 2026 the CCS 3-Day Guarantee gives every eligible family ≥72 subsidised hours/fortnight including vacation care, structurally increasing school-holiday care demand while supply-side booking remains fragmented.

## 2. Product thesis

A two-sided platform: **free SaaS-lite booking tools for providers** (the supply hook and the source of live availability data) + **a parent-facing marketplace** with real-time availability and one-cart checkout (the demand surface and revenue engine). Wedge categories are **variety-seeking** (holiday programs, birthday parties) where repeat behaviour naturally routes through the aggregator; loyalty categories (term classes) are explicitly out of scope.

## 3. Goals & non-goals

**Goals (12 months)**
- G1: Own live availability for ≥100 Perth holiday-program providers.
- G2: ≥2,500 marketplace bookings across two school-holiday cycles.
- G3: Birthday-party vertical live with ≥40 bookable venues/mobile providers.
- G4: Provider NPS high enough that providers self-serve their next holiday program without sales touch.

**Non-goals (explicitly out of scope until Phase 3+)**
- CCS-approved care intermediation, session reporting, or subsidy plumbing.
- Term-time class enrolments (swim/gym/dance).
- Nanny/babysitting, childcare placement.
- Native iOS/Android apps (PWA first).
- Eastern-states expansion before Perth density is proven.

## 4. Personas

**P1 — "The Juggler" (primary demand).** Dual-income Perth parent, 1–3 kids aged 4–12. Plans holidays 1–4 weeks out, evenings on mobile. Wants: see everything near me, filter by kid's age and date, book in minutes, one receipt. Fears: dodgy operators, cancellations, losing money.

**P2 — "The Studio Owner" (primary supply).** Runs an art/sport/STEM micro-business, 1–5 staff. Sells 40–200 holiday-program seats per cycle via Facebook + spreadsheet. Wants: fill sessions, stop admin, get paid upfront. Fears: platform fees on customers she'd have gotten anyway, double bookings, losing her customer relationship.

**P3 — "The Party Planner" parent.** Books one party/year/child, $400–700 AOV. Wants: compare venues, real slots, deposit online, guest headcount changes late.

**P4 — "The Venue Manager" (party supply).** Trampoline park / play centre / mobile entertainer. Has peak-weekend scarcity and dead midweek capacity. Wants: fill the calendar, reduce phone-tag quoting.

**P5 — Internal ops/admin (you).** Approves providers, moderates content, resolves disputes, monitors payouts.

## 5. Success metrics

| Metric | MVP gate (spring holidays) | 12 months |
|---|---|---|
| Providers live w/ real inventory | 15–20 | 100+ |
| Sessions listed per cycle | 60+ | 800+ |
| Bookings per cycle | 150 presold | 1,200/cycle |
| GMV per cycle | A$10k | A$120k |
| Take rate realised | 8–10% | 10–12% blended |
| Parent repeat rate (next cycle) | — | ≥35% |
| Provider relist rate (next cycle) | ≥70% | ≥85% |
| Booking completion (checkout funnel) | ≥65% | ≥75% |
| Disintermediation proxy (repeat parent books same provider off-platform) | monitored | <25% of repeats |

## 6. Scope & phasing

- **Phase 0 — MVP (build Aug, live for late-Sep WA spring holidays):** holiday programs only, browse/search/book/pay, provider self-serve listing + roster, email notifications, admin console. Sections marked **[MVP]**.
- **Phase 1 (summer holidays cycle):** reviews, waitlists, refund automation, SMS, promo codes, saved kids profiles improvements, provider analytics. **[P1]**
- **Phase 2:** birthday-party vertical (quote + instant-book), embeddable provider widget, memberships/packs, off-peak deals. **[P2]**
- **Phase 3:** CCS-adjacent features, KidSport voucher integration (WA), AI planner ("fill my week"), multi-city. **[P3]**

---

## 7. Feature specification — Parent side

### 7.1 Discovery & search [MVP]
- Browse without an account. SEO-indexable listing pages (SSR).
- Search by suburb/postcode with PostGIS radius; filters: date(s), child age, category (sport/art/STEM/drama/outdoor/other), price range, session type (half/full day), drop-off vs parent-stays.
- List + map views; date-first browsing ("show me Tuesday 30 Sep").
- Each card shows: photo, price, age range, times, distance, and **live seats remaining** — the core differentiator; never show stale availability.
- Empty-state: suggest nearby dates/categories; capture email for alerts. [P1]

### 7.2 Listing detail page [MVP]
- Sessions calendar with per-session capacity; what-to-bring; drop-off/pickup instructions; venue map; provider profile with verification badges (ABN verified, WWCC on file, insurance on file); cancellation policy in plain language.
- Structured age gating: booking blocked if child's age outside range (override flag per provider).

### 7.3 Family profile [MVP]
- Guardian account (email + password; Google/Apple SSO [P1]; phone-OTP reuse from Karvon auth module if practical).
- Child profiles: first name, DOB, allergies/medical notes, emergency contact, photo consent flag. Data minimisation: no child surname required at MVP; no child photos stored.
- Multiple guardians per family. [P1]

### 7.4 Cart & checkout [MVP]
- Multi-session, multi-child, multi-provider cart; single payment.
- Stripe Payment Element; Apple/Google Pay. Card surcharge or absorbed fee — decision D-03.
- Per-session forms injected at checkout (provider-defined required fields, e.g., swim ability).
- Order confirmation: single email with per-day itinerary + .ics calendar attachments.
- GST-compliant tax invoice (platform fee is +GST; provider pricing GST handling per provider settings).

### 7.5 Manage bookings [MVP]
- Bookings dashboard: upcoming/past; per-booking details; cancel within policy window (auto-refund via Stripe [P1]; manual at MVP).
- Reminders: T-48h and T-3h email; SMS [P1]; push (PWA) [P2].

### 7.6 Reviews & trust [P1]
- Verified-booking-only reviews, 1–5 stars + text; provider right-of-reply; moderation queue; no child names/photos in review content (auto-screen).

### 7.7 Waitlist [P1]
- Join waitlist on sold-out session; auto-offer with 4h claim window on cancellation.

### 7.8 Weekend "Discover" tab [P2]
- Free layer: this-weekend feed of one-off family events/venues (markets, open days, library events) — content-ingested, not bookable; exists for weekly retention between holiday cycles.

### 7.9 AI planner [P3]
- "Fill my week": constraints in (kids' ages, dates, budget, location, interests), itinerary out, one-tap book. Claude API; only over live inventory.

## 8. Feature specification — Provider side

### 8.1 Onboarding & verification [MVP]
- Self-serve signup; org model (reuse Karvon org/membership patterns): organisation → members → roles (owner/staff).
- Required before go-live: ABN (validated via ABR lookup), WA Working with Children Check numbers for all child-facing staff (manual verification at MVP; expiry tracking), public liability insurance certificate upload (manual review), bank details via Stripe Connect Express.
- Admin approval gate before first listing publishes.

### 8.2 Listings & sessions [MVP]
- Create program → generate sessions (date, start/end, capacity, price, min/max age, venue).
- Bulk session creation across a holiday range; duplicate-from-last-cycle (critical for relist rate).
- Instant publish/unpublish; capacity edits with oversell guard.

### 8.3 Bookings & roster [MVP]
- Live roster per session: child first name, age, allergies/medical, emergency contact, custom form answers.
- Printable/CSV roster; morning-of check-in list (tap to mark attended [P1]).
- Provider-initiated cancellation flow: cancels session → auto-notify + refund all bookings + platform flags reliability score.

### 8.4 Payments & payouts [MVP]
- Stripe Connect Express, destination charges; platform fee 10% + GST on marketplace-originated bookings.
- Payout after session completion + N days (dispute buffer). Decision D-04: N=2 vs weekly batch.
- Fee exemption for provider-imported customers (fairness lever vs P2 fear of "fees on my own customers"): bookings via provider's direct link = 0–2% processing-only tier. [P1]

### 8.5 Comms [P1]
- Broadcast message to a session's booked families (template-guarded); automated "what to bring" T-24h.
- No free-text parent↔provider chat at MVP (support burden + safeguarding surface); structured Q&A on listing instead. [P2 for chat, if ever]

### 8.6 Analytics [P1]
- Fill rate per session, revenue per cycle, new-vs-returning families, search impressions.

### 8.7 Embeddable booking widget [P2]
- Provider embeds "Book now" on their own site/Facebook; inventory unified; anti-disintermediation because their direct channel now runs on your rails.

### 8.8 Promotions [P1/P2]
- Promo codes, early-bird pricing, sibling discounts [P1]; last-minute/off-peak automatic markdowns with member-only visibility (yield tool) [P2].

## 9. Feature specification — Birthday parties [P2]

- Two supply modes: **instant-book slots** (venues with fixed packages: slot calendar, package picker, per-head pricing, deposit % at booking, balance auto-charged T-7d) and **request-to-quote** (mobile entertainers: structured brief → quotes → accept → deposit).
- Guest count adjustable until T-72h; digital invites with RSVP [P3].
- Party-specific policies: weather clause for outdoor, minimum spend.

## 10. Feature specification — Admin panel [MVP]

Design principle: **the admin panel is a first-class product surface from day one, not an afterthought.** Every operational lever the founder needs during the first two holiday cycles must be adjustable at runtime through the panel — zero code changes, zero redeploys for configuration. Solo-operator reality: support, moderation, and configuration all happen here, often from mobile, often during live holiday periods.

### 10.1 Runtime configuration console [MVP]
All settings versioned, bounded, and audit-logged (INV-11); changes take effect without deploy:
- **Commercial:** platform fee % (bounded 0–20), payment surcharge mode, payout delay N days, refund policy floor parameters.
- **Inventory mechanics:** seat-hold TTL, per-provider oversell-guard overrides (off by default), waitlist claim window [P1].
- **Taxonomy:** activity categories, age-band presets, badge definitions — editable lists, not enums in code.
- **Calendar:** WA school-holiday periods (drives "this holidays" surfaces and cycle-based analytics); additional states later.
- **Content:** homepage featured collections, announcement banner, email/SMS template editing with preview + test-send, FAQ/help articles.
- **Feature flags:** full flags UI (reuse Karvon flags module) — per-flag on/off, percentage rollout, per-org targeting.
- **Search tuning:** default radius, ranking weights (fill-rate boost, distance decay) as editable parameters.

### 10.2 Ops consoles [MVP]
- **Provider management:** approval queue (ABN/WWCC/insurance doc review with side-by-side viewer), verification status, expiry alerts, suspension switch, reliability score, internal notes (lightweight CRM).
- **Guardian/user management:** lookup by email/phone/child first name, account status, booking history, data-deletion request workflow (APP compliance), duplicate-account merge [P1].
- **Bookings console:** search by any dimension; manual refund (full/partial) with reason codes; move a child between sessions (capacity-checked via inventory module); resend confirmations/.ics; cancel with notification control.
- **Listing moderation:** publish/unpublish, photo-rights takedown, claim-wording review.
- **Incident register:** complaints tagged safeguarding vs service-quality; safeguarding → 24h review SLA, one-click provider suspension, exportable incident timeline.
- **Payments ops:** payout holds, dispute/chargeback tracker, Stripe Radar review queue, reconciliation view (bookings ↔ charges ↔ payouts).
- **Fraud basics:** booking velocity limits (configurable in 10.1), flagged-account queue.

### 10.3 Impersonation ("view as / act as") [MVP]
The single most valuable support tool for a solo operator: see exactly what a guardian or provider sees, and fix things on their behalf.

- **Two modes:** `view-as` (read-only render of the user's UI; mutation endpoints rejected) and `act-as` (full actions, for hands-on support like completing a stuck booking).
- **Mechanics:** admin panel issues a scoped impersonation token via a token-exchange endpoint; the JWT carries both `sub` (impersonated user) and `impersonator_id` (true actor). Sessions are time-boxed (30 min default, configurable in 10.1) and end explicitly or on expiry.
- **Visibility:** persistent banner in the impersonated UI ("Support session active — acting as <name>"); impersonation state is never invisible in the rendered product.
- **Blocked during impersonation (both modes):** changing the user's email/phone/password, viewing saved payment instruments, adding/altering provider bank details, initiating payouts, deleting the account, exporting child data. These require the real user or a documented break-glass procedure.
- **Notification suppression:** actions taken while impersonating suppress customer-facing emails/SMS by default (explicit per-action override with reason), so support work never spams the customer.
- **Audit (INV-10):** every impersonation session and every action within it is audit-logged with the true actor, target, mode, duration, and per-action detail; sessions touching roster/child data are flagged for weekly review.
- **Provider-side too:** impersonating a provider org member is equally supported — most onboarding support ("my session isn't showing") is provider-side.

### 10.4 Admin platform requirements [MVP]
- Admin is a separate Quasar app surface (`apps/web` admin routes or dedicated shell) behind admin-role auth; MFA required for admin accounts.
- Every admin mutation goes through the same module service layer as the product (no side-door SQL), and every one lands in `audit`.
- Mobile-usable: approval queue, incident register, refunds, and impersonation must work from a phone during live holiday periods.

## 11. Trust, safety & compliance

- **WWCC (WA):** stored check numbers + expiry; block roster assignment of unverified staff; re-verify on expiry. This is table stakes for parent trust and the #1 badge on listing pages.
- **Child data (Privacy Act 1988 / APPs):** collect minimum (first name, DOB, medical/emergency); encrypt at rest; guardian-only access; no child data in analytics events; deletion on request; data breach response plan. No marketing to children.
- **Insurance:** provider public-liability certificate required; platform's own insurance + T&Cs positioning platform as booking agent, not care provider — legal review required (Open question O-2).
- **Refund policy floor:** platform-mandated minimums (e.g., full refund if provider cancels; illness policy guidance) overriding provider-set policies.
- **Reviews integrity:** verified bookings only; defamation takedown process.

## 12. System design notes

- **Modules (core/ui split, import-linter enforced):** identity, org, catalog (programs/sessions), inventory (capacity/holds), booking, payments, roster, notifications, search/geo, admin, config (runtime settings, versioned), flags, audit.
- **Inventory correctness is the product.** Seat holds with TTL at checkout (SELECT ... FOR UPDATE or Postgres advisory locks), idempotent booking creation, oversell impossible by constraint (`bookings_count <= capacity` enforced transactionally).
- **Search:** Postgres FTS + PostGIS (his home turf); no external search engine at MVP.
- **Data model (core):** `organisation, venue(geog), program, session(capacity, price, age_min/max), guardian, child, booking(status), booking_child, payment, payout, wwcc_record, insurance_doc, review, waitlist_entry, audit_event, feature_flag, platform_setting(versioned), impersonation_session`.
- **Notifications:** transactional email (Postmark/SES) MVP; SMS (Twilio) P1.
- **Payments:** Stripe Connect Express, destination charges, application fee; webhooks idempotent.
- **PWA:** Quasar SSR for SEO on listing pages + installable PWA shell.
- **Environments:** docker-compose everything; one ADR per module per house rules.

## 13. Analytics & instrumentation [MVP]

Event taxonomy: `search_performed, listing_viewed, session_selected, checkout_started, checkout_completed, booking_cancelled, provider_signup, listing_published, session_filled`. Funnel dashboards per cycle. No child PII in events.

## 14. Launch plan (tied to WA spring holidays, late Sep–Oct 2026)

| Window | Milestone |
|---|---|
| Now → early Aug | Kill-criteria gate: provider sprint (15–20 signed LOIs), presale test |
| Aug | Build MVP (scope §7.1–7.5, §8.1–8.4, §10) |
| ~4 wks pre-holidays | Providers publish programs (matches current market behaviour of late schedule releases) |
| 2–3 wks pre | Demand push: Perth parent Facebook groups, school P&C giveback pilots (rev-share to P&C per booking), local press |
| Holidays | Ops on-call; daily fill-rate review |
| Post-cycle | Relist campaign for summer; Phase 1 build |

## 15. Risks (top 5)

1. **Adverse supply selection** — sold-out brands don't list. Mitigate: free tools + duplicate-from-last-cycle + direct-channel fee exemption.
2. **Disintermediation** — mitigate: variety-seeking categories, widget (P2), value in roster/payments not just demand.
3. **Seasonality cashflow** — 4 spikes/year; parties (P2) smooth.
4. **Safeguarding incident on-platform** — mitigate: WWCC gating, insurance verification, incident SLA; reputational risk is existential, over-invest here.
5. **Incumbent response** — WeTeachMe verticalises or an OSHC giant opens marketplace. Mitigate: speed + Perth density + provider tooling depth.

## 16. Open questions / decisions

- D-01: Working name & ASIC/trademark check ("Juggle" placeholder).
- D-02: Take rate 10% vs 12%; GST-inclusive display rules (ACCC pricing compliance — must show total price).
- D-03: Payment surcharge pass-through vs absorbed.
- D-04: Payout timing (T+2 vs weekly).
- O-1: Entity structure & platform terms (booking agent vs merchant of record) — solicitor.
- O-2: Insurance posture for the platform itself — broker.
- O-3: Reuse Karvon phone-OTP auth module vs email-first (parents on desktop at night?).
- O-4: KidSport voucher acceptance mechanics (WA) — P3 research.

## 17. Explicitly out of scope (restated to prevent creep)

CCS session reporting, term-class enrolment, chat/DMs at MVP, native apps, childcare staffing, interstate launch, provider financing.
