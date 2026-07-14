"""Party Planner service (ADR-0011): vote-to-book birthday planning.

A planning layer *on top of* ``PartyBooking`` — it creates no holds and moves no money
(INV-1/INV-2). At resolution the host confirms a package winner through the unchanged
``parties.service.book_slot`` deposit flow. State transitions that could race (resolve vs
vote, double-confirm) serialise on a ``SELECT … FOR UPDATE`` of the ``party_plan`` row.

Privacy (INV-13): votes are anonymous — no function returns vote-by-invite; the only place
vote→invite is dereferenced is the edge-6 re-vote nudge (host-invisible). Guest child data
never lives in this module (INV-3); marketing consent is written to a detached, purge-exempt
table (edge 7).
"""

import re
import secrets
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway
from juggle.modules.parties.core import service as parties_service
from juggle.modules.parties.core.models import (
    PartyBooking,
    PartyBookingStatus,
    PartyPackage,
    PartySlot,
    PartySlotStatus,
)
from juggle.modules.party_planner.core import schemas
from juggle.modules.party_planner.core.models import (
    PartyPlan,
    PlanInvite,
    PlanInviteMode,
    PlanInviteStatus,
    PlanMarketingConsent,
    PlanOption,
    PlanOptionKind,
    PlanReaction,
    PlanRsvp,
    PlanStatus,
    PlanThrottle,
    PlanVote,
)
from juggle.modules.payments.core.gateway import PaymentGateway, PaymentIntentResult
from juggle.settings import get_settings

# --- Errors ----------------------------------------------------------------


class PlanNotFound(Exception):
    pass


class NotPlanHost(Exception):
    pass


class PlanNotDraft(Exception):
    pass


class PlanNotOpen(Exception):
    pass


class PlanNotResolved(Exception):
    pass


class TooManyOptions(Exception):
    pass


class DuplicateCustomOption(Exception):
    pass


class OptionNotFound(Exception):
    pass


class OptionNotEligible(Exception):
    """The chosen option can't be booked (custom, voided, wrong plan, or slot in the past)."""


class DeadlineInvalid(Exception):
    pass


class NotOpenable(Exception):
    """Plan can't leave draft (too few options, no package option, or no valid deadline)."""


class InviteNotFound(Exception):
    pass


class RsvpClosed(Exception):
    """The plan is not open, or the deadline has passed."""


class InviteNotApproved(Exception):
    pass


class RateLimited(Exception):
    pass


class SlotUnavailable(Exception):
    pass


class InvalidTheme(Exception):
    pass


class InvalidReaction(Exception):
    pass


# --- Constants / sanitisation ----------------------------------------------

AVATAR_KEYS = frozenset(
    {"dino", "rocket", "unicorn", "star", "cat", "dog", "robot", "fox", "panda", "owl",
     "dragon", "balloon"}
)
# Party page templates (theme skins). A style choice only — the child's gender is never stored;
# the frontend `planTheme.ts` carries the matching colours/decorations for each key.
THEMES = frozenset(
    {"default", "unicorn", "princess", "superhero", "dino", "space", "rainbow", "mermaid", "jungle"}
)
# Host-toggleable page widgets, in display order. The vote panel is always shown (not a member).
WIDGET_KEYS_ORDER = ("welcome", "countdown", "board", "reveal_venue")
WIDGET_KEYS = frozenset(WIDGET_KEYS_ORDER)
# Fixed emoji set for one-tap reactions — a closed allow-list (no arbitrary strings on the
# public page).
REACTION_EMOJIS = frozenset({"❤️", "🎉", "🔥", "😍", "👍", "🤩"})
_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")  # strip HTML tags (defense-in-depth; the JSON client escapes too)
# Small profanity mask — the public page is untrusted input (edge 8). Not exhaustive; the
# length cap + URL strip are the load-bearing controls.
_PROFANITY = ("fuck", "shit", "cunt", "bitch", "bastard", "dick", "asshole")
_PROFANITY_RE = re.compile("|".join(re.escape(w) for w in _PROFANITY), re.IGNORECASE)


def _sanitise_public_text(raw: str, maxlen: int) -> str:
    """Strip URLs, collapse whitespace, mask profanity, cap length (edge 8). Applies to any
    guest-authored string that renders on the public plan page (custom option, nickname)."""
    text = _TAG_RE.sub("", raw)
    text = _URL_RE.sub("", text)
    text = " ".join(text.split())
    text = _PROFANITY_RE.sub("***", text)
    return text[:maxlen]


def _token() -> str:
    return secrets.token_urlsafe(32)  # 256-bit opaque (INV-13)


def _now() -> datetime:
    return datetime.now(UTC)


# --- Internal helpers ------------------------------------------------------


def get_plan(db: Session, plan_id: uuid.UUID) -> PartyPlan | None:
    return db.get(PartyPlan, plan_id)


def _lock_plan(db: Session, plan_id: uuid.UUID) -> PartyPlan | None:
    """Row-lock the plan so status transitions serialise (resolve vs vote; double-confirm)."""
    return db.execute(
        select(PartyPlan).where(PartyPlan.id == plan_id).with_for_update()
    ).scalar_one_or_none()


def _require_host(plan: PartyPlan, actor_id: uuid.UUID) -> None:
    if plan.host_user_id != actor_id:
        raise NotPlanHost(str(plan.id))


def _share_link(plan: PartyPlan, invite_token: str | None = None) -> str:
    base = get_settings().public_base_url.rstrip("/")
    url = f"{base}/parties/plan/{plan.token}"
    return f"{url}?invite={invite_token}" if invite_token else url


def _option_label(db: Session, option: PlanOption | None) -> str:
    if option is None:
        return "the top pick"
    if option.kind is PlanOptionKind.custom:
        return option.custom_text or "a custom party"
    package = db.get(PartyPackage, option.package_id) if option.package_id else None
    return package.name if package is not None else "the party"


def _responded_count(db: Session, plan_id: uuid.UUID) -> int:
    """Approved invites that actually RSVP'd — the real participation metric for the nudge (edge 3),
    so pre-approved email invites don't mask a silent room."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(PlanRsvp)
            .join(PlanInvite, PlanRsvp.plan_invite_id == PlanInvite.id)
            .where(
                PlanInvite.plan_id == plan_id,
                PlanInvite.status == PlanInviteStatus.approved,
            )
        ) or 0
    )


def _approved_invites(db: Session, plan_id: uuid.UUID) -> list[PlanInvite]:
    return list(
        db.scalars(
            select(PlanInvite).where(
                PlanInvite.plan_id == plan_id,
                PlanInvite.status == PlanInviteStatus.approved,
            )
        )
    )


def _options(db: Session, plan_id: uuid.UUID, *, include_voided: bool = False) -> list[PlanOption]:
    stmt = select(PlanOption).where(PlanOption.plan_id == plan_id)
    if not include_voided:
        stmt = stmt.where(PlanOption.voided.is_(False))
    return list(db.scalars(stmt.order_by(PlanOption.position)))


def _earliest_package_slot(db: Session, plan_id: uuid.UUID) -> datetime | None:
    starts = [
        slot.starts_at
        for opt in _options(db, plan_id)
        if opt.kind is PlanOptionKind.package and opt.slot_id is not None
        and (slot := db.get(PartySlot, opt.slot_id)) is not None
    ]
    return min(starts) if starts else None


def _validate_deadline(db: Session, plan_id: uuid.UUID, deadline: datetime, now: datetime) -> None:
    if deadline <= now:
        raise DeadlineInvalid("deadline must be in the future")
    earliest = _earliest_package_slot(db, plan_id)
    if earliest is not None:
        gap = timedelta(hours=config_service.party_planner_min_deadline_gap_hours(db))
        if deadline > earliest - gap:
            raise DeadlineInvalid("deadline too close to the earliest option's slot")


def _tally(db: Session, plan_id: uuid.UUID) -> Counter[uuid.UUID]:
    """Votes per option, counting only APPROVED invites' votes on NON-VOIDED options
    (INV-12 — the tally is a real count; pending/removed voters and voided options excluded)."""
    live_option_ids = {opt.id for opt in _options(db, plan_id)}
    rows = db.execute(
        select(PlanVote.plan_option_id)
        .join(PlanInvite, PlanVote.plan_invite_id == PlanInvite.id)
        .where(
            PlanVote.plan_id == plan_id,
            PlanInvite.status == PlanInviteStatus.approved,
        )
    ).scalars()
    counter: Counter[uuid.UUID] = Counter()
    for option_id in rows:
        if option_id in live_option_ids:
            counter[option_id] += 1
    return counter


def _approved_yes_headcount(db: Session, plan_id: uuid.UUID) -> int:
    """Σ kid_count over APPROVED, attending RSVPs — the confirm-headcount prefill (critic #3)."""
    total = db.execute(
        select(func.coalesce(func.sum(PlanRsvp.kid_count), 0))
        .join(PlanInvite, PlanRsvp.plan_invite_id == PlanInvite.id)
        .where(
            PlanInvite.plan_id == plan_id,
            PlanInvite.status == PlanInviteStatus.approved,
            PlanRsvp.attending.is_(True),
        )
    ).scalar_one()
    return int(total)


# --- Host: plan lifecycle --------------------------------------------------


def create_plan(db: Session, *, host_id: uuid.UUID, theme: str = "default") -> PartyPlan:
    plan = PartyPlan(
        host_user_id=host_id, status=PlanStatus.draft, theme=theme[:40], approval_required=False
    )
    db.add(plan)
    db.flush()
    return plan


def set_theme(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, theme: str
) -> PartyPlan:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    if theme not in THEMES:
        raise InvalidTheme(theme)
    plan.theme = theme
    db.flush()
    return plan


def update_page(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID,
    template: str, title: str, message: str, hero_avatar: str | None, widgets: list[str],
) -> PartyPlan:
    """Full-state update of the host-customizable party page. Host-only, editable while draft/open.
    Title/message are untrusted host text → sanitised (HTML/URL strip, profanity mask, length cap),
    like custom-option text (edge 8); they must never carry a child's real name (guidance, like the
    nickname board field). Template/avatar/widgets are validated against closed allow-lists.
    """
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    if template not in THEMES:
        raise InvalidTheme(template)
    clean_title = _sanitise_public_text(title, config_service.party_planner_page_title_maxlen(db))
    clean_msg = _sanitise_public_text(
        message, config_service.party_planner_page_message_maxlen(db)
    )
    plan.theme = template
    plan.page_title = clean_title or None
    plan.page_message = clean_msg or None
    plan.hero_avatar = hero_avatar if hero_avatar in AVATAR_KEYS else None
    # Keep only known widget keys, de-duplicated in the canonical WIDGET_KEYS order.
    enabled = {w for w in widgets if w in WIDGET_KEYS}
    plan.page_widgets = [w for w in WIDGET_KEYS_ORDER if w in enabled]
    db.flush()
    return plan


def list_host_plans(db: Session, host_id: uuid.UUID) -> list[PartyPlan]:
    return list(
        db.scalars(
            select(PartyPlan)
            .where(PartyPlan.host_user_id == host_id)
            .order_by(PartyPlan.created_at.desc())
        )
    )


def _editable(plan: PartyPlan) -> None:
    if plan.status not in (PlanStatus.draft, PlanStatus.open):
        raise PlanNotDraft(str(plan.id))


def add_package_option(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID,
    package_id: uuid.UUID, slot_id: uuid.UUID,
) -> PlanOption:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    existing = _options(db, plan_id)
    if len(existing) >= config_service.party_planner_max_options(db):
        raise TooManyOptions(str(plan_id))
    slot = db.get(PartySlot, slot_id)
    package = db.get(PartyPackage, package_id)
    if slot is None or package is None or slot.package_id != package_id:
        raise OptionNotFound(str(slot_id))
    position = 1 + max((o.position for o in existing), default=0)
    option = PlanOption(
        plan_id=plan_id, kind=PlanOptionKind.package, package_id=package_id,
        slot_id=slot_id, position=position,
    )
    db.add(option)
    db.flush()
    # Adding an option can retroactively breach the deadline gap (critic #12).
    if plan.deadline_at is not None:
        _validate_deadline(db, plan_id, plan.deadline_at, _now())
    return option


def add_custom_option(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, text: str
) -> PlanOption:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    existing = _options(db, plan_id)
    if len(existing) >= config_service.party_planner_max_options(db):
        raise TooManyOptions(str(plan_id))
    if any(o.kind is PlanOptionKind.custom for o in existing):
        raise DuplicateCustomOption(str(plan_id))  # max one custom option (LOCKED decision)
    clean = _sanitise_public_text(text, config_service.party_planner_custom_option_maxlen(db))
    if not clean:
        raise OptionNotEligible("empty custom option")
    position = 1 + max((o.position for o in existing), default=0)
    option = PlanOption(
        plan_id=plan_id, kind=PlanOptionKind.custom, custom_text=clean, position=position
    )
    db.add(option)
    db.flush()
    return option


def remove_option(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, option_id: uuid.UUID
) -> PlanOption:
    """Void an option. If the plan is open and it had votes, those voters get re-vote nudges
    (edge 6, sent by the scheduler); the vote rows are simply excluded from the live tally."""
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    option = db.get(PlanOption, option_id)
    if option is None or option.plan_id != plan_id:
        raise OptionNotFound(str(option_id))
    option.voided = True
    db.flush()
    return option


def set_ranking(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, ordered_option_ids: list[uuid.UUID]
) -> PartyPlan:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    valid = {o.id for o in _options(db, plan_id, include_voided=True)}
    plan.birthday_kid_ranking = [str(oid) for oid in ordered_option_ids if oid in valid]
    db.flush()
    return plan


def set_deadline(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, deadline_at: datetime,
    now: datetime | None = None,
) -> PartyPlan:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    _editable(plan)
    _validate_deadline(db, plan_id, deadline_at, now or _now())
    plan.deadline_at = deadline_at
    db.flush()
    return plan


def open_plan(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, now: datetime | None = None
) -> PartyPlan:
    now = now or _now()
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    if plan.status is not PlanStatus.draft:
        raise PlanNotDraft(str(plan_id))
    options = _options(db, plan_id)
    if len(options) < 2:
        raise NotOpenable("need at least 2 options")
    if not any(o.kind is PlanOptionKind.package for o in options):
        raise NotOpenable("need at least 1 bookable package option")
    if plan.deadline_at is None:
        raise NotOpenable("a deadline is required")
    _validate_deadline(db, plan_id, plan.deadline_at, now)
    plan.token = _token()
    plan.status = PlanStatus.open
    db.flush()
    return plan


def extend_deadline(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, now: datetime | None = None
) -> PartyPlan:
    now = now or _now()
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    if plan.status is not PlanStatus.open or plan.deadline_at is None:
        raise PlanNotOpen(str(plan_id))
    proposed = plan.deadline_at + timedelta(hours=config_service.party_planner_extend_hours(db))
    _validate_deadline(db, plan_id, proposed, now)  # extend only if the gap still holds (edge 3/5)
    plan.deadline_at = proposed
    db.flush()
    return plan


# --- Host: invites + approval queue ----------------------------------------


def add_email_invites(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID,
    recipients: list[tuple[str, str]], email_gateway: EmailGateway | None = None,
) -> list[PlanInvite]:
    """Host-entered per-guest invites are trusted → approved immediately (no queue). Each guest is
    emailed a link with their invite token so they land pre-recognised (transactional, INV-13)."""
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    invites = []
    for email, name in recipients:
        invite = PlanInvite(
            plan_id=plan_id, mode=PlanInviteMode.email, email=email.strip().lower(),
            parent_name=_sanitise_public_text(name, 120) or "Guest",
            status=PlanInviteStatus.approved, token=_token(),
        )
        db.add(invite)
        invites.append(invite)
    db.flush()
    if email_gateway is not None and plan.token:
        for invite in invites:
            notifications_service.notify_planner_invite(
                db, to_email=invite.email, link=_share_link(plan, invite.token),
                gateway=email_gateway,
            )
    return invites


def set_invite_status(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID,
    invite_id: uuid.UUID, status: PlanInviteStatus,
) -> PlanInvite:
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    invite = db.get(PlanInvite, invite_id)
    if invite is None or invite.plan_id != plan_id:
        raise InviteNotFound(str(invite_id))
    invite.status = status
    db.flush()
    return invite


# --- Public (tokenized) ----------------------------------------------------


def get_plan_by_token(db: Session, token: str) -> PartyPlan | None:
    if not token:
        return None
    return db.scalar(select(PartyPlan).where(PartyPlan.token == token))


def get_invite_by_token(db: Session, token: str) -> PlanInvite | None:
    if not token:
        return None
    return db.scalar(select(PlanInvite).where(PlanInvite.token == token))


def _check_rate(db: Session, *, scope_key: str, now: datetime, limit: int) -> None:
    """Persistent fixed 1-hour window per scope (IP/token). Raises RateLimited when exceeded."""
    row = db.execute(
        select(PlanThrottle).where(PlanThrottle.scope_key == scope_key).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        db.add(PlanThrottle(scope_key=scope_key, window_started_at=now, count=1))
        db.flush()
        return
    if now - row.window_started_at >= timedelta(hours=1):
        row.window_started_at = now
        row.count = 1
        db.flush()
        return
    if row.count >= limit:
        raise RateLimited(scope_key)
    row.count += 1
    db.flush()


def _rsvp_open(plan: PartyPlan, now: datetime) -> None:
    if plan.status is not PlanStatus.open or plan.deadline_at is None or now >= plan.deadline_at:
        raise RsvpClosed(str(plan.id))


def rate_limit(db: Session, *, scope_key: str, now: datetime | None = None) -> None:
    """Public entrypoint rate-limit guard (routes call this per IP + per token)."""
    _check_rate(
        db, scope_key=scope_key, now=now or _now(),
        limit=config_service.party_planner_rsvp_rate_per_hour(db),
    )


def open_rsvp(
    db: Session, *, plan: PartyPlan, parent_name: str, email: str, attending: bool,
    kid_count: int, nickname: str | None, avatar_key: str | None,
    marketing_opt_in: bool, now: datetime | None = None,
) -> PlanInvite:
    """Open-link self-RSVP. Anyone with the share link is auto-approved (unless the plan opts into
    approval) so they can vote immediately, and marketing consent is recorded to the detached,
    purge-exempt store (edge 7).

    No confirmation email is sent from this unauthenticated endpoint: the guest is already on the
    page (their invite token is returned + stored client-side), and emailing the address they typed
    would be an email-bombing vector now that RSVPs auto-approve (an attacker could spray
    confirmations to arbitrary addresses). The winning-party announcement still reaches them at
    resolution via the invite's stored email.
    """
    now = now or _now()
    _rsvp_open(plan, now)
    maxlen = config_service.party_planner_custom_option_maxlen(db)
    status = PlanInviteStatus.pending if plan.approval_required else PlanInviteStatus.approved
    invite = PlanInvite(
        plan_id=plan.id, mode=PlanInviteMode.open, email=email.strip().lower(),
        parent_name=_sanitise_public_text(parent_name, 120) or "Guest",
        status=status, token=_token(),
    )
    db.add(invite)
    db.flush()
    _write_rsvp(db, invite=invite, attending=attending, kid_count=kid_count,
                nickname=nickname, avatar_key=avatar_key, maxlen=maxlen)
    if marketing_opt_in:
        db.add(PlanMarketingConsent(email=email.strip().lower(), source="party_planner_rsvp"))
        db.flush()
    return invite


def edit_rsvp(
    db: Session, *, invite: PlanInvite, plan: PartyPlan, attending: bool, kid_count: int,
    nickname: str | None, avatar_key: str | None, now: datetime | None = None,
) -> PlanRsvp:
    now = now or _now()
    if invite.status in (PlanInviteStatus.removed, PlanInviteStatus.blocked):
        raise RsvpClosed(str(invite.id))  # opaque — no "you're blocked" oracle
    _rsvp_open(plan, now)
    maxlen = config_service.party_planner_custom_option_maxlen(db)
    return _write_rsvp(db, invite=invite, attending=attending, kid_count=kid_count,
                       nickname=nickname, avatar_key=avatar_key, maxlen=maxlen)


def _write_rsvp(
    db: Session, *, invite: PlanInvite, attending: bool, kid_count: int,
    nickname: str | None, avatar_key: str | None, maxlen: int,
) -> PlanRsvp:
    clean_nick = _sanitise_public_text(nickname, min(maxlen, 80)) if nickname else None
    clean_avatar = avatar_key if avatar_key in AVATAR_KEYS else None
    rsvp = db.scalar(select(PlanRsvp).where(PlanRsvp.plan_invite_id == invite.id))
    if rsvp is None:
        rsvp = PlanRsvp(plan_invite_id=invite.id, attending=attending,
                        kid_count=max(0, min(kid_count, 50)),
                        nickname=clean_nick, avatar_key=clean_avatar)
        db.add(rsvp)
    else:
        rsvp.attending = attending
        rsvp.kid_count = max(0, min(kid_count, 50))
        rsvp.nickname = clean_nick
        rsvp.avatar_key = clean_avatar
    db.flush()
    return rsvp


def cast_vote(
    db: Session, *, invite: PlanInvite, option_id: uuid.UUID, now: datetime | None = None
) -> PlanVote:
    """One editable vote per invite (UNIQUE(plan_invite_id)); gated to the open window and an
    approved invite. Serialised on the plan row so a vote can't slip in as resolve tallies."""
    now = now or _now()
    plan = _lock_plan(db, invite.plan_id)
    if plan is None:
        raise PlanNotFound(str(invite.plan_id))
    _rsvp_open(plan, now)
    if invite.status is not PlanInviteStatus.approved:
        raise InviteNotApproved(str(invite.id))
    option = db.get(PlanOption, option_id)
    if option is None or option.plan_id != plan.id or option.voided:
        raise OptionNotEligible(str(option_id))
    vote = db.scalar(select(PlanVote).where(PlanVote.plan_invite_id == invite.id))
    if vote is None:
        vote = PlanVote(plan_id=plan.id, plan_invite_id=invite.id, plan_option_id=option_id)
        db.add(vote)
    else:
        vote.plan_option_id = option_id  # edit in place (edge 2)
    db.flush()
    return vote


def react(
    db: Session, *, invite: PlanInvite, option_id: uuid.UUID, emoji: str,
    now: datetime | None = None,
) -> bool:
    """Toggle a one-tap emoji reaction on an option. Approved invite + open window + closed emoji
    allow-list. Returns True if the reaction is now on, False if it was toggled off. Aggregate
    counts only are ever surfaced (unattributed)."""
    now = now or _now()
    plan = _lock_plan(db, invite.plan_id)
    if plan is None:
        raise PlanNotFound(str(invite.plan_id))
    _rsvp_open(plan, now)
    if invite.status is not PlanInviteStatus.approved:
        raise InviteNotApproved(str(invite.id))
    if emoji not in REACTION_EMOJIS:
        raise InvalidReaction(emoji)
    option = db.get(PlanOption, option_id)
    if option is None or option.plan_id != plan.id or option.voided:
        raise OptionNotEligible(str(option_id))
    existing = db.scalar(
        select(PlanReaction).where(
            PlanReaction.plan_invite_id == invite.id,
            PlanReaction.plan_option_id == option_id,
            PlanReaction.emoji == emoji,
        )
    )
    if existing is not None:
        db.delete(existing)
        db.flush()
        return False
    db.add(PlanReaction(
        plan_id=plan.id, plan_option_id=option_id, plan_invite_id=invite.id, emoji=emoji
    ))
    db.flush()
    return True


def _reactions(db: Session, plan_id: uuid.UUID) -> dict[uuid.UUID, dict[str, int]]:
    """Aggregate emoji reaction counts per option (unattributed)."""
    rows = db.execute(
        select(PlanReaction.plan_option_id, PlanReaction.emoji, func.count())
        .where(PlanReaction.plan_id == plan_id)
        .group_by(PlanReaction.plan_option_id, PlanReaction.emoji)
    ).all()
    result: dict[uuid.UUID, dict[str, int]] = {}
    for option_id, emoji, count in rows:
        result.setdefault(option_id, {})[emoji] = int(count)
    return result


# --- Resolution + reconciliation (scheduler tick) --------------------------


def _pick_winner(db: Session, plan: PartyPlan) -> uuid.UUID | None:
    """Winner = most votes among non-voided options; ties broken by the birthday kid's ranking
    (earliest ranked, voided entries skipped); an unbreakable tie → None (host chooses)."""
    counter = _tally(db, plan.id)
    live = _options(db, plan.id)
    if not live:
        return None
    # No votes → every option ties at 0; ranking still lets the host's favourite win.
    top = max((counter[o.id] for o in live), default=0)
    tied = [o.id for o in live if counter[o.id] == top]
    if len(tied) == 1:
        return tied[0]
    ranking = [uuid.UUID(x) for x in plan.birthday_kid_ranking]
    live_ids = {o.id for o in live}
    for oid in ranking:
        if oid in tied and oid in live_ids:
            return oid
    return None  # genuine tie — reveal says "host is choosing"


def resolve_due_plans(
    db: Session, *, now: datetime | None = None, email_gateway: EmailGateway | None = None
) -> int:
    """Flip open plans whose deadline has passed to resolved and compute the winner. Idempotent
    (only open→resolved); clock-controlled via ``now`` for tests. Announces the reveal to every
    approved invitee once (``announced_at`` marker)."""
    now = now or _now()
    due = db.scalars(
        select(PartyPlan.id).where(
            PartyPlan.status == PlanStatus.open, PartyPlan.deadline_at <= now
        )
    ).all()
    resolved = 0
    for plan_id in due:
        plan = _lock_plan(db, plan_id)
        if plan is None or plan.status is not PlanStatus.open:
            continue  # someone else resolved it under the lock
        plan.winning_option_id = _pick_winner(db, plan)
        plan.status = PlanStatus.resolved
        plan.resolved_at = now
        db.flush()
        if email_gateway is not None and plan.announced_at is None:
            winner = db.get(PlanOption, plan.winning_option_id) if plan.winning_option_id else None
            label = (
                _option_label(db, winner) if winner is not None
                else "a tie — the host will decide"
            )
            for invite in _approved_invites(db, plan.id):
                notifications_service.notify_planner_reveal(
                    db, to_email=invite.email, winner_label=label,
                    link=_share_link(plan, invite.token), gateway=email_gateway,
                )
            plan.announced_at = now
            db.flush()
        resolved += 1
    return resolved


def send_planner_nudges(
    db: Session, *, now: datetime | None = None, email_gateway: EmailGateway
) -> tuple[int, int]:
    """Two once-only scheduler nudges (ADR-0011 edges 3 & 6): a T-24h low-participation nudge to the
    host, and a re-vote nudge to anyone who voted for an option the host later voided. Returns
    (low_rsvp_sent, revote_sent). The re-vote path is the one place vote→invite is dereferenced —
    an internal use only; it never surfaces on any host/admin view."""
    now = now or _now()
    threshold = config_service.party_planner_low_rsvp_threshold(db)
    low_sent = 0
    revote_sent = 0

    # Low-RSVP nudge: open plans inside the last 24h with too few RSVPs, not yet nudged.
    open_plans = db.scalars(
        select(PartyPlan.id).where(PartyPlan.status == PlanStatus.open)
    ).all()
    for plan_id in open_plans:
        plan = _lock_plan(db, plan_id)
        if plan is None or plan.status is not PlanStatus.open or plan.deadline_at is None:
            continue
        if plan.low_rsvp_nudge_sent_at is not None or now < plan.deadline_at - timedelta(hours=24):
            continue
        if now >= plan.deadline_at:
            continue
        responded = _responded_count(db, plan_id)
        if responded < threshold:
            host = identity_service.get_user(db, plan.host_user_id)
            if host is not None:
                notifications_service.notify_planner_low_rsvp(
                    db, user_id=host.id, to_email=host.email, rsvp_count=responded,
                    link=_share_link(plan), gateway=email_gateway,
                )
                low_sent += 1
        plan.low_rsvp_nudge_sent_at = now
        db.flush()

    # Re-vote nudge: voided options with votes from approved invites, not yet nudged.
    stale_options = db.scalars(
        select(PlanOption).where(
            PlanOption.voided.is_(True), PlanOption.revote_nudge_sent_at.is_(None)
        )
    ).all()
    for option in stale_options:
        plan = db.get(PartyPlan, option.plan_id)
        if plan is None or plan.status is not PlanStatus.open:
            continue
        voters = db.scalars(
            select(PlanInvite)
            .join(PlanVote, PlanVote.plan_invite_id == PlanInvite.id)
            .where(
                PlanVote.plan_option_id == option.id,
                PlanInvite.status == PlanInviteStatus.approved,
            )
        ).all()
        for invite in voters:
            notifications_service.notify_planner_revote(
                db, to_email=invite.email, link=_share_link(plan, invite.token),
                gateway=email_gateway,
            )
            revote_sent += 1
        option.revote_nudge_sent_at = now
        db.flush()

    return low_sent, revote_sent


def _event_reference_date(db: Session, plan: PartyPlan) -> datetime | None:
    """The date the party effectively happened (or would have) — the purge clock (edge 7)."""
    if plan.winning_option_id is not None:
        option = db.get(PlanOption, plan.winning_option_id)
        if option is not None and option.slot_id is not None:
            slot = db.get(PartySlot, option.slot_id)
            if slot is not None:
                return slot.starts_at
    latest: datetime | None = None
    for opt in _options(db, plan.id, include_voided=True):
        if opt.slot_id and (slot := db.get(PartySlot, opt.slot_id)) is not None:
            latest = slot.starts_at if latest is None else max(latest, slot.starts_at)
    # Floor on created_at so a slot-less/abandoned draft still purges (never retained forever).
    return latest or plan.resolved_at or plan.created_at


def purge_expired_plan_pii(db: Session, *, now: datetime | None = None) -> int:
    """Anonymise guest PII N days after the event (edge 7). Anonymises **in place** (rather than
    deleting) so aggregate vote/reaction counts survive PII-free; the detached marketing consent is
    never touched. Idempotent via ``purged_at``. Clock-controlled via ``now`` for tests."""
    now = now or _now()
    horizon = timedelta(days=config_service.party_planner_purge_days(db))
    candidates = db.scalars(
        select(PartyPlan.id).where(PartyPlan.purged_at.is_(None))
    ).all()
    purged = 0
    for plan_id in candidates:
        plan = _lock_plan(db, plan_id)
        if plan is None or plan.purged_at is not None:
            continue
        event_date = _event_reference_date(db, plan)
        if event_date is None or now < event_date + horizon:
            continue
        emails: list[str] = []
        for invite in db.scalars(select(PlanInvite).where(PlanInvite.plan_id == plan_id)):
            if invite.email:
                emails.append(invite.email)
            invite.email = ""
            invite.parent_name = "(removed)"
            rsvp = db.scalar(select(PlanRsvp).where(PlanRsvp.plan_invite_id == invite.id))
            if rsvp is not None:
                rsvp.nickname = None
                rsvp.avatar_key = None
        # Also scrub the guest address from the transactional planner delivery logs (edge 7).
        notifications_service.purge_planner_recipients(db, emails=emails)
        plan.purged_at = now
        db.flush()
        purged += 1
    return purged


def sweep_stale_resolved(db: Session, *, now: datetime | None = None) -> int:
    """Terminal cleanup: a resolved plan whose winning package slot has passed (host never
    booked), or whose winner is custom/unresolved, becomes expired_unbooked once past the slot.
    Also reconciles a booked plan whose underlying booking was cancelled back to resolved."""
    now = now or _now()
    swept = 0
    # Reconcile falsely-"booked" plans (deposit failed/abandoned → booking cancelled) — critic #7.
    booked = db.scalars(
        select(PartyPlan.id).where(PartyPlan.status == PlanStatus.booked)
    ).all()
    for plan_id in booked:
        plan = _lock_plan(db, plan_id)
        if plan is None or plan.status is not PlanStatus.booked or plan.booking_id is None:
            continue
        booking = db.get(PartyBooking, plan.booking_id)
        if booking is not None and booking.status is PartyBookingStatus.cancelled:
            plan.status = PlanStatus.resolved
            plan.booking_id = None
            db.flush()
    # Expire resolved plans the host never booked once the (winning) slot is in the past.
    resolved = db.scalars(
        select(PartyPlan.id).where(PartyPlan.status == PlanStatus.resolved)
    ).all()
    for plan_id in resolved:
        plan = _lock_plan(db, plan_id)
        if plan is None or plan.status is not PlanStatus.resolved:
            continue
        if _resolution_passed(db, plan, now):
            plan.status = PlanStatus.expired_unbooked
            db.flush()
            swept += 1
    return swept


def _resolution_passed(db: Session, plan: PartyPlan, now: datetime) -> bool:
    if plan.winning_option_id is None:
        # Unbroken tie: fall back to the latest option slot as the "no longer actionable" bound.
        latest = None
        for opt in _options(db, plan.id):
            if opt.slot_id and (slot := db.get(PartySlot, opt.slot_id)) is not None:
                latest = slot.starts_at if latest is None else max(latest, slot.starts_at)
        return latest is not None and now >= latest
    option = db.get(PlanOption, plan.winning_option_id)
    if option is None or option.kind is PlanOptionKind.custom or option.slot_id is None:
        return True  # custom winner is never bookable here → terminal
    slot = db.get(PartySlot, option.slot_id)
    return slot is not None and now >= slot.starts_at


# --- Host: confirm the winning booking -------------------------------------


def confirm_booking(
    db: Session, *, plan_id: uuid.UUID, actor_id: uuid.UUID, gateway: PaymentGateway,
    option_id: uuid.UUID | None = None, headcount: int | None = None,
    now: datetime | None = None, email_gateway: EmailGateway | None = None,
) -> tuple[PartyPlan, PartyBooking, PaymentIntentResult]:
    """Book the winning (or host-overridden) PACKAGE option through parties.book_slot. Serialised
    on the plan row so a double-submit can't create two bookings/deposits (critic #1). Returns the
    deposit PaymentIntent so the host can settle it (live) or dev-confirm it."""
    now = now or _now()
    plan = _lock_plan(db, plan_id)
    if plan is None:
        raise PlanNotFound(str(plan_id))
    _require_host(plan, actor_id)
    if plan.status is not PlanStatus.resolved:
        raise PlanNotResolved(str(plan_id))
    announced_winner = plan.winning_option_id  # what the invitees were told (None = tie)
    chosen_id = option_id or plan.winning_option_id
    if chosen_id is None:
        raise OptionNotEligible("no winner selected (tie) — choose an option")
    option = db.get(PlanOption, chosen_id)
    if (
        option is None or option.plan_id != plan_id or option.voided
        or option.kind is not PlanOptionKind.package or option.slot_id is None
    ):
        raise OptionNotEligible(str(chosen_id))
    slot = db.get(PartySlot, option.slot_id)
    if slot is None or slot.status is not PartySlotStatus.available or slot.starts_at <= now:
        raise SlotUnavailable(str(option.slot_id))  # sold out mid-plan, or slot already passed
    count = headcount if headcount is not None else _approved_yes_headcount(db, plan_id)
    booking, intent = parties_service.book_slot(
        db, slot_id=slot.id, guardian_id=actor_id, headcount=count, gateway=gateway
    )
    plan.winning_option_id = option.id
    plan.booking_id = booking.id
    plan.status = PlanStatus.booked
    db.flush()
    # If the host overrode a real announced winner, tell the guests it changed (edge 4).
    if (
        email_gateway is not None and announced_winner is not None
        and option.id != announced_winner
    ):
        label = _option_label(db, option)
        for invite in _approved_invites(db, plan.id):
            notifications_service.notify_planner_change(
                db, to_email=invite.email, new_label=label,
                link=_share_link(plan, invite.token), gateway=email_gateway,
            )
    return plan, booking, intent


# --- View builders (Pydantic) ----------------------------------------------


def _favourite_option_id(plan: PartyPlan, live_ids: set[uuid.UUID]) -> uuid.UUID | None:
    for raw in plan.birthday_kid_ranking:
        oid = uuid.UUID(raw)
        if oid in live_ids:
            return oid
    return None


def _option_views(
    db: Session, plan: PartyPlan, *, include_voided: bool = False
) -> list[schemas.OptionView]:
    tally = _tally(db, plan.id)
    reactions = _reactions(db, plan.id)
    options = _options(db, plan.id, include_voided=include_voided)
    favourite = _favourite_option_id(plan, {o.id for o in options if not o.voided})
    views: list[schemas.OptionView] = []
    for opt in options:
        view = schemas.OptionView(
            id=opt.id, kind=opt.kind.value, position=opt.position, voided=opt.voided,
            custom_text=opt.custom_text, votes=tally.get(opt.id, 0),
            is_favourite=(opt.id == favourite), reactions=reactions.get(opt.id, {}),
        )
        if opt.kind is PlanOptionKind.package and opt.package_id and opt.slot_id:
            package = db.get(PartyPackage, opt.package_id)
            slot = db.get(PartySlot, opt.slot_id)
            if package is not None:
                view.package_id = package.id
                view.package_name = package.name
                view.per_head_price_cents = package.per_head_price_cents
                venue = catalog_service.get_venue(db, package.venue_id)
                view.venue_name = venue.name if venue else None
            if slot is not None:
                view.starts_at = slot.starts_at
                view.ends_at = slot.ends_at
                view.available = slot.status is PartySlotStatus.available  # INV-12 live
        views.append(view)
    return views


def deadline_warnings(db: Session, plan: PartyPlan) -> list[str]:
    """Non-blocking warnings if the deadline lands inside a winning option's balance (T-7d) or
    adjustment (T-72h) window — the host can still confirm, but with less runway (edge 5)."""
    if plan.deadline_at is None:
        return []
    warnings: list[str] = []
    balance_days = config_service.party_balance_offset_days(db)
    for opt in _options(db, plan.id):
        if opt.kind is not PlanOptionKind.package or opt.slot_id is None:
            continue
        slot = db.get(PartySlot, opt.slot_id)
        if slot is None:
            continue
        package = db.get(PartyPackage, opt.package_id) if opt.package_id else None
        name = package.name if package is not None else "an option"
        if plan.deadline_at > slot.starts_at - timedelta(hours=72):
            warnings.append(f"Deadline is inside the 72h guest-count window for {name}")
        elif plan.deadline_at > slot.starts_at - timedelta(days=balance_days):
            warnings.append(f"Deadline is inside the balance-charge window for {name}")
    return warnings


def host_plan_view(db: Session, plan: PartyPlan) -> schemas.PlanView:
    invites = db.scalars(
        select(PlanInvite).where(PlanInvite.plan_id == plan.id).order_by(PlanInvite.created_at)
    ).all()
    invite_views: list[schemas.HostInviteView] = []
    for inv in invites:
        rsvp = db.scalar(select(PlanRsvp).where(PlanRsvp.plan_invite_id == inv.id))
        invite_views.append(
            schemas.HostInviteView(
                id=inv.id, mode=inv.mode.value, parent_name=inv.parent_name, email=inv.email,
                status=inv.status.value,
                attending=rsvp.attending if rsvp else None,
                kid_count=rsvp.kid_count if rsvp else None,
                nickname=rsvp.nickname if rsvp else None,
                avatar_key=rsvp.avatar_key if rsvp else None,
            )
        )
    return schemas.PlanView(
        id=plan.id, status=plan.status.value, deadline_at=plan.deadline_at, theme=plan.theme,
        approval_required=plan.approval_required, share_token=plan.token,
        share_path=(f"/parties/plan/{plan.token}" if plan.token else None),
        winning_option_id=plan.winning_option_id, booking_id=plan.booking_id,
        ranking=[uuid.UUID(x) for x in plan.birthday_kid_ranking],
        options=_option_views(db, plan, include_voided=True), invites=invite_views,
        rsvp_yes_headcount=_approved_yes_headcount(db, plan.id),
        deadline_warnings=deadline_warnings(db, plan),
        page=_page_view(plan),
    )


def _page_view(plan: PartyPlan) -> schemas.PartyPageView:
    """The host-customizable party page config, echoed to both host + public views. Empty
    ``page_widgets`` means 'all widgets on' (the default before a host customises)."""
    widgets = list(plan.page_widgets) if plan.page_widgets else list(WIDGET_KEYS_ORDER)
    return schemas.PartyPageView(
        template=plan.theme, title=plan.page_title, message=plan.page_message,
        hero_avatar=plan.hero_avatar, widgets=widgets,
    )


def _board(db: Session, plan_id: uuid.UUID) -> tuple[list[schemas.BoardEntry], int]:
    """Pseudonymous who's-in board: approved, attending RSVPs — nickname/avatar only (INV-13)."""
    rows = db.execute(
        select(PlanRsvp.nickname, PlanRsvp.avatar_key)
        .join(PlanInvite, PlanRsvp.plan_invite_id == PlanInvite.id)
        .where(
            PlanInvite.plan_id == plan_id,
            PlanInvite.status == PlanInviteStatus.approved,
            PlanRsvp.attending.is_(True),
        )
        .order_by(PlanRsvp.created_at)
    ).all()
    board = [schemas.BoardEntry(nickname=n, avatar_key=a) for n, a in rows]
    return board, len(board)


def public_plan_view(
    db: Session, plan: PartyPlan, *, now: datetime | None = None
) -> schemas.PublicPlanView:
    now = now or _now()
    board, count = _board(db, plan.id)
    is_open = (
        plan.status is PlanStatus.open and plan.deadline_at is not None and now < plan.deadline_at
    )
    is_tie = plan.status is PlanStatus.resolved and plan.winning_option_id is None
    return schemas.PublicPlanView(
        status=plan.status.value, is_open=is_open, deadline_at=plan.deadline_at, theme=plan.theme,
        options=_option_views(db, plan), board=board, rsvp_count=count,
        winner_option_id=plan.winning_option_id, is_tie=is_tie, page=_page_view(plan),
    )


def invite_self_view(
    db: Session, invite: PlanInvite, *, now: datetime | None = None
) -> schemas.InviteSelfView:
    plan = db.get(PartyPlan, invite.plan_id)
    assert plan is not None
    rsvp = db.scalar(select(PlanRsvp).where(PlanRsvp.plan_invite_id == invite.id))
    has_voted = (
        db.scalar(select(func.count()).select_from(PlanVote).where(
            PlanVote.plan_invite_id == invite.id)) or 0
    ) > 0
    return schemas.InviteSelfView(
        invite_token=invite.token, status=invite.status.value, has_voted=has_voted,
        rsvp=(
            schemas.RsvpView(attending=rsvp.attending, kid_count=rsvp.kid_count,
                             nickname=rsvp.nickname, avatar_key=rsvp.avatar_key)
            if rsvp else None
        ),
        plan=public_plan_view(db, plan, now=now),
    )

