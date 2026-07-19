# Handoff — 2026-07-12 — Party Planner Milestone D (lifecycle + purge) · ADR-0011 COMPLETE

## Scope
Milestone D — the final leg of the Party Planner: transactional lifecycle emails, the two
scheduler nudges, and the retention purge. With this, **ADR-0011 A→B→C→D is complete.** On
`feat/party-planner-D` (stacked on `feat/party-planner-C`), **not pushed**.

## What was built

### Notifications (in the `notifications` module; stub gateway now, real templates)
All transactional, all child-PII-free (INV-13). New `notify_planner_*` builders:
- **invite** (email-mode) — each guest emailed a link carrying their invite token, so they land
  pre-recognised;
- **RSVP confirmation** (see S3 below for the gating);
- **reveal** — announced to every approved invitee on resolution, **once** (`announced_at`);
- **change of plans** — when the host overrides a real announced winner at confirm;
- **low-participation nudge** — to the host at T-24h if responders < threshold, **once**
  (`low_rsvp_nudge_sent_at`);
- **re-vote nudge** — to the approved voters of an option the host voided, **once per option**
  (`revote_nudge_sent_at`). This is the one place vote→invite is dereferenced — internal only,
  surfaced on no view.

### Scheduler tick
Now: resolve + announce (passes the email gateway) → `send_planner_nudges` → `sweep_stale_resolved`
→ `purge_expired_plan_pii`. `JobSummary` gained `plans_purged`.

### Purge (edge 7)
`purge_expired_plan_pii` anonymises guest PII **in place** N days after the event
(`party_planner_purge_days`, default 30): clears email / parent_name / nickname / avatar on
`plan_invite` + `plan_rsvp`, **and scrubs the guest address from the transactional planner delivery
logs**. Aggregate vote/reaction counts survive (anonymise-in-place, no cascade); the detached
`plan_marketing_consent` is never touched; idempotent via `purged_at`; the event date **floors on
`created_at`** so slot-less/abandoned drafts still purge.

### Frontend
The invitee page reads `?invite=<token>` from the emailed link so email-invited guests are
recognised without re-RSVPing.

## Adversarial review (purge + notification PII) — 1 blocker + 3 should-fix, all fixed
- **B1 (blocker):** slot-less/abandoned drafts never purged → PII retained forever. Fixed: event
  reference date floors on `created_at`. Locked by `test_abandoned_draft_with_invites_still_purges`.
- **S1:** guest emails lingered in `NotificationLog`. Fixed: `notifications_service.
  purge_planner_recipients` scrubs guest-facing planner log rows at purge (host's own low-RSVP log
  left intact).
- **S2:** low-RSVP nudge counted pre-approved email invites → never fired for email-invited plans.
  Fixed: counts actual responders (`_responded_count`). Locked by a dedicated test.
- **S3:** open-link RSVP emailed attacker-supplied addresses before approval (email-bombing). Fixed:
  the confirmation is only sent to already-approved invites (default `approval_required=True` plans
  send nothing to pending open-link RSVPs).

## Verification
- Backend `make check` **262 passed** (34 planner tests), mypy strict, import-linter **2 contracts
  KEPT**.
- Frontend `vue-tsc` + `vite build` + `vitest` (23) green.
- (Housekeeping: cleared two leaked committed `party_plan` drafts from the shared dev DB and made
  the purge tests assert on the specific plan rather than a global count.)

## ADR-0011 status: COMPLETE (A→B→C→D)
- **A** core model + API · **B** host + invitee surfaces · **C** gamified layer · **D** lifecycle +
  purge. All behind the `party_planner` flag (**OFF in prod** until the real email gateway lands).

## Known gaps / next
- **Real email gateway** is the remaining hard go-live dependency (emails run through the stub /
  FakeEmailGateway today; the flag stays OFF in prod until real delivery is wired).
- **Live deposit path** (Payment Element in the manage page) still needs Stripe test keys to verify
  end-to-end (dev one-click confirm is verified).
- **Post-tie final-pick notice** (N3): after a tie the invitees aren't told the host's final choice
  (a change-of-plans is only sent when overriding a real winner) — a small product follow-up.
- **Branch chain** `feat/party-planner-{A,B,C,D}` (+ the `docs/party-planner-adr` base) is unpushed;
  merge order docs → A → B → C → D.
