"""Business logic for the identity module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import CursorResult, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.identity.core.models import (
    AuthThrottle,
    Child,
    GuardianLink,
    OtpChallenge,
    RefreshToken,
    UserAccount,
    UserStatus,
)
from juggle.modules.identity.core.schemas import ChildCreate, CoGuardianOut
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import SmsGateway
from juggle.security import (
    generate_otp_code,
    generate_refresh_token,
    hash_otp_code,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from juggle.settings import get_settings


class EmailAlreadyExists(Exception):
    """Raised when signing up with an email that is already registered."""


class ReservedEmail(Exception):
    """The email is in a reserved namespace (phone-account / deleted sentinels).

    Blocking these at sign-up stops an attacker pre-registering the address the
    SMS flow would mint for a victim's number (which would otherwise squat it)."""


class InvalidRefreshToken(Exception):
    """The presented refresh token is unknown, expired, or already revoked."""


class RefreshTokenReuse(InvalidRefreshToken):
    """A revoked token was replayed — the whole token family has been revoked.

    Distinct from ``InvalidRefreshToken`` because the caller must *commit* the
    revocation (it happened while rejecting the request), so the route returns
    the 401 without raising past the transaction boundary."""


class OtpRateLimited(Exception):
    """A sign-in code was requested again inside the resend cooldown."""


class OtpSendThrottled(Exception):
    """An OTP send was blocked by a per-number/per-IP/global cap (abuse/cost)."""


class InvalidOtp(Exception):
    """No matching, unexpired, unconsumed code — or too many wrong attempts."""


class CoGuardianNotFound(Exception):
    """No account with that email to invite as a co-guardian."""


class CannotLinkSelf(Exception):
    """A guardian cannot add themselves as a co-guardian."""


class AlreadyLinked(Exception):
    """These two accounts already have a co-guardian link."""


class LinkNotFound(Exception):
    """No such co-guardian link for this user."""


# Reserved e-mail domain for phone-first accounts. `.invalid` is reserved by
# RFC 2606 (guaranteed non-deliverable), and sign-up refuses it — so the address
# the SMS flow mints for a number can never be pre-registered by someone else.
_PHONE_ACCOUNT_DOMAIN = "phone.juggle.invalid"
_RESERVED_EMAIL_SUFFIXES = (".invalid",)


def _is_reserved_email(email: str) -> bool:
    return email.strip().lower().endswith(_RESERVED_EMAIL_SUFFIXES)


def create_guardian(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
) -> UserAccount:
    """Create an email+password guardian.

    Phone is deliberately NOT accepted here: a phone number is only ever bound to
    an account by proving possession through the SMS one-time-code flow, so an
    email sign-up can't squat someone else's (unverified) number.
    """
    if _is_reserved_email(email):
        raise ReservedEmail(email)
    if session.scalar(select(UserAccount).where(UserAccount.email == email)) is not None:
        raise EmailAlreadyExists(email)
    user = UserAccount(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, *, email: str, password: str) -> UserAccount | None:
    user = session.scalar(select(UserAccount).where(UserAccount.email == email))
    if user is None or user.password_hash is None:
        return None
    if user.status is not UserStatus.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user(session: Session, user_id: uuid.UUID) -> UserAccount | None:
    return session.get(UserAccount, user_id)


# --- refresh tokens (DB-backed, revocable, rotated on use) --------------------


def issue_refresh_token(session: Session, *, user_id: uuid.UUID) -> str:
    """Mint a new refresh token for a session/device; return the raw secret
    (only its hash is stored). The caller pairs it with a short access token."""
    settings = get_settings()
    raw = generate_refresh_token()
    token = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
    )
    session.add(token)
    session.flush()
    return raw


def rotate_refresh_token(session: Session, *, raw: str) -> tuple[UserAccount, str]:
    """Exchange a valid refresh token for a fresh access+refresh pair.

    Rotation invalidates the presented token. Presenting an already-revoked token
    means it was replayed (or the account was compromised): we revoke every token
    for that user as a safety response. Raises ``InvalidRefreshToken`` otherwise.
    """
    # Lock the row: two concurrent rotations of the same token must serialise, so
    # the second sees revoked_at set and trips reuse detection instead of both
    # succeeding and silently forking the token family.
    token = session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_refresh_token(raw))
        .with_for_update()
    )
    if token is None:
        raise InvalidRefreshToken("unknown token")

    now = datetime.now(UTC)
    if token.revoked_at is not None:
        # Replay of a rotated/logged-out token — sever the whole family. This
        # write must survive the rejected request, so it's raised as a distinct
        # type the route commits (see RefreshTokenReuse).
        revoke_all_refresh_tokens(session, user_id=token.user_id)
        raise RefreshTokenReuse("token reuse detected")
    if token.expires_at <= now:
        raise InvalidRefreshToken("expired token")

    user = session.get(UserAccount, token.user_id)
    if user is None or user.status is not UserStatus.active:
        raise InvalidRefreshToken("inactive account")

    new_raw = issue_refresh_token(session, user_id=user.id)
    token.revoked_at = now
    token.replaced_by_id = session.scalar(
        select(RefreshToken.id).where(RefreshToken.token_hash == hash_refresh_token(new_raw))
    )
    session.flush()
    return user, new_raw


def revoke_refresh_token(session: Session, *, raw: str) -> bool:
    """Revoke a single refresh token (logout). Idempotent; unknown → False."""
    token = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw))
    )
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        session.flush()
    return True


def revoke_all_refresh_tokens(session: Session, *, user_id: uuid.UUID) -> int:
    """Revoke every live refresh token for a user (force-logout everywhere)."""
    now = datetime.now(UTC)
    tokens = session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    for token in tokens:
        token.revoked_at = now
    session.flush()
    return len(tokens)


def prune_expired_auth(session: Session, *, now: datetime) -> int:
    """Delete auth rows that can no longer do anything, so the tables don't grow
    without bound (run from the maintenance tick).

    Removes **expired** refresh tokens (an expired token is already rejected, so
    dropping it loses nothing — revoked-but-unexpired rows are KEPT so replay of a
    live-window token still trips reuse detection), spent/expired OTP challenges,
    and stale throttle windows. Returns the number of rows deleted."""
    otp_cutoff = now - timedelta(days=1)
    statements = (
        delete(RefreshToken).where(RefreshToken.expires_at < now),
        delete(OtpChallenge).where(OtpChallenge.expires_at < otp_cutoff),
        delete(AuthThrottle).where(AuthThrottle.window_started_at < otp_cutoff),
    )
    deleted = 0
    for stmt in statements:
        deleted += cast("CursorResult[object]", session.execute(stmt)).rowcount
    session.flush()
    return deleted


# --- SMS one-time-code sign-in (PRD §7.2) ------------------------------------

_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str) -> str:
    """Best-effort E.164-ish normalisation so a number resolves to one account.

    WA/AU-friendly: a leading ``0`` national number becomes ``+61``; a bare
    number with no ``+`` is assumed already-international and gets a ``+``.
    """
    trimmed = raw.strip()
    keep_plus = trimmed.startswith("+")
    digits = _DIGITS.sub("", trimmed)
    if not keep_plus and digits.startswith("0") and len(digits) == 10:
        digits = "61" + digits[1:]
    return "+" + digits


def _hit_rate_limit(
    session: Session, *, scope_key: str, now: datetime, window: timedelta, limit: int
) -> bool:
    """Persistent fixed-window counter for ``scope_key``. Returns True when the
    request would exceed ``limit`` (and does NOT record it); else records a hit
    and returns False. Row-locked so concurrent requests can't both slip under."""
    row = session.execute(
        select(AuthThrottle).where(AuthThrottle.scope_key == scope_key).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        # First request for this scope. FOR UPDATE can't gap-lock a not-yet-existing
        # row, so two concurrent creators race the unique index — guard the insert in
        # a savepoint and fall through to the existing-row path on conflict (rather
        # than 500). The nested rollback discards the pending row (SQLAlchemy expunges
        # it), leaving the outer transaction usable.
        session.add(AuthThrottle(scope_key=scope_key, window_started_at=now, count=1))
        try:
            with session.begin_nested():
                session.flush()
            return False
        except IntegrityError:
            row = session.execute(
                select(AuthThrottle).where(AuthThrottle.scope_key == scope_key).with_for_update()
            ).scalar_one()
    if now - row.window_started_at >= window:
        row.window_started_at = now
        row.count = 1
        session.flush()
        return False
    if row.count >= limit:
        return True
    row.count += 1
    session.flush()
    return False


def _enforce_otp_send_limits(
    session: Session, *, normalized: str, ip: str | None, now: datetime
) -> None:
    """Block SMS-bombing / runaway Twilio cost: caps per number/day, per IP/hour,
    and a global per-hour ceiling — beyond the short per-number resend cooldown."""
    settings = get_settings()
    hour, day = timedelta(hours=1), timedelta(days=1)
    checks: list[tuple[str, timedelta, int]] = [
        (f"otp:num:{normalized}", day, settings.otp_max_per_number_per_day),
        ("otp:global", hour, settings.otp_global_max_per_hour),
    ]
    if ip:
        checks.append((f"otp:ip:{ip}", hour, settings.otp_max_per_ip_per_hour))
    for scope_key, window, limit in checks:
        if _hit_rate_limit(session, scope_key=scope_key, now=now, window=window, limit=limit):
            raise OtpSendThrottled(scope_key)


def request_otp(
    session: Session, *, phone: str, gateway: SmsGateway, ip: str | None = None
) -> None:
    """Generate a sign-in code for ``phone`` and text it. Rate-limited by a
    per-number resend cooldown plus per-number/per-IP/global send caps to blunt
    SMS-bombing and Twilio-cost abuse."""
    settings = get_settings()
    normalized = normalize_phone(phone)
    now = datetime.now(UTC)

    recent = session.scalar(
        select(OtpChallenge)
        .where(OtpChallenge.phone == normalized)
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    )
    if recent is not None:
        age = (now - recent.created_at).total_seconds()
        if age < settings.otp_resend_cooldown_seconds:
            raise OtpRateLimited(str(int(settings.otp_resend_cooldown_seconds - age)))

    _enforce_otp_send_limits(session, normalized=normalized, ip=ip, now=now)

    code = generate_otp_code()
    challenge = OtpChallenge(
        phone=normalized,
        code_hash=hash_otp_code(code),
        expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
    )
    session.add(challenge)
    session.flush()
    notifications_service.send_login_code(
        session,
        phone=normalized,
        code=code,
        ttl_minutes=settings.otp_ttl_minutes,
        gateway=gateway,
    )


def verify_otp(session: Session, *, phone: str, code: str) -> UserAccount:
    """Check a code and resolve (or create) the account for that phone.

    On success the challenge is consumed. A wrong code counts against the
    attempt cap; exhausting it burns the challenge. Raises ``InvalidOtp``."""
    settings = get_settings()
    normalized = normalize_phone(phone)
    now = datetime.now(UTC)

    # Lock the challenge row so parallel guesses can't both read the same
    # ``attempts`` and each pass the cap (brute-force via concurrency).
    challenge = session.scalar(
        select(OtpChallenge)
        .where(
            OtpChallenge.phone == normalized,
            OtpChallenge.consumed_at.is_(None),
            OtpChallenge.expires_at > now,
        )
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if challenge is None:
        raise InvalidOtp("no active code")

    challenge.attempts += 1
    if challenge.attempts > settings.otp_max_attempts:
        challenge.consumed_at = now  # burn it — no more guesses on this code
        session.flush()
        raise InvalidOtp("too many attempts")
    if challenge.code_hash != hash_otp_code(code):
        session.flush()
        raise InvalidOtp("wrong code")

    challenge.consumed_at = now
    session.flush()
    return _find_or_create_by_phone(session, phone=normalized)


def _find_or_create_by_phone(session: Session, *, phone: str) -> UserAccount:
    """Existing account for this (normalised) phone, or a fresh phone-first one.

    A phone-first account has no password (OTP-only) and a placeholder email it
    can change later — the phone is the real identifier. Data-minimising: no name
    collected at sign-in."""
    user = session.scalar(select(UserAccount).where(UserAccount.phone == phone))
    if user is not None:
        if user.status is not UserStatus.active:
            raise InvalidOtp("inactive account")
        return user
    # Placeholder in the reserved `.invalid` namespace that sign-up refuses, so it
    # can't have been pre-registered (see create_guardian). The phone is the true
    # identifier. Guard the insert against a concurrent first-OTP for the same
    # number: the phone UNIQUE constraint makes one racer's flush fail — catch it
    # and return the row the winner created rather than 500.
    placeholder_email = f"sms-{phone.lstrip('+')}@{_PHONE_ACCOUNT_DOMAIN}"
    user = UserAccount(email=placeholder_email, phone=phone, password_hash=None)
    session.add(user)
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(UserAccount).where(UserAccount.phone == phone))
        if existing is None:
            raise
        if existing.status is not UserStatus.active:
            raise InvalidOtp("inactive account") from None
        return existing
    return user


def search_users(session: Session, *, query: str, limit: int = 20) -> list[UserAccount]:
    """Find users by email or name fragment — an admin support lookup (PRD §10.2)."""
    like = f"%{query}%"
    return list(
        session.scalars(
            select(UserAccount)
            .where(or_(UserAccount.email.ilike(like), UserAccount.full_name.ilike(like)))
            .order_by(UserAccount.email)
            .limit(max(1, min(limit, 50)))
        )
    )


def add_child(session: Session, *, guardian_id: uuid.UUID, data: ChildCreate) -> Child:
    child = Child(guardian_id=guardian_id, **data.model_dump())
    session.add(child)
    session.flush()
    return child


class AccountDeleted(Exception):
    """A data-deleted account cannot be suspended or reinstated — §10.2 deletion is
    irreversible, and the row no longer carries the PII a real account needs."""


def set_account_status(
    session: Session, *, user_id: uuid.UUID, status: UserStatus
) -> UserAccount | None:
    """Move an account between ``active`` and ``suspended``.

    Suspension is enforced in three places already — ``authenticate`` refuses a
    login, ``rotate_refresh_token`` refuses a refresh, and ``deps`` re-checks live
    status on *every* request — so this only has to flip the column and pull the
    live sessions. Revoking the refresh tokens is what makes it immediate rather
    than eventual: the access token dies on its next request, and there is nothing
    left to mint a new one with.

    ``deleted`` is a terminal state in both directions (raises ``AccountDeleted``).
    """
    if status is UserStatus.deleted:
        raise AccountDeleted("use delete_account for §10.2 deletion")
    user = session.get(UserAccount, user_id)
    if user is None:
        return None
    if user.status is UserStatus.deleted:
        raise AccountDeleted(str(user_id))
    user.status = status
    if status is UserStatus.suspended:
        revoke_all_refresh_tokens(session, user_id=user_id)
    session.flush()
    return user


def deactivate_account(session: Session, *, user_id: uuid.UUID) -> bool:
    """Anonymise + disable a login (no PII, can't authenticate). Keeps the row —
    bookings/audit reference it. Shared by delete (§10.2) and merge. No audit."""
    user = session.get(UserAccount, user_id)
    if user is None:
        return False
    user.email = f"deleted-{user.id}@removed.invalid"
    user.full_name = None
    user.phone = None
    user.password_hash = None
    user.mfa_secret = None
    user.status = UserStatus.deleted
    revoke_all_refresh_tokens(session, user_id=user_id)
    session.flush()
    return True


def delete_account(session: Session, *, user_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
    """APP data-deletion (PRD §10.2): irreversibly strip a guardian's personal
    data and their children's, and disable login. The rows are kept (bookings and
    payments reference them for financial/audit records) but carry no PII.
    Returns False if there's no such user. Audited with the true actor."""
    if not deactivate_account(session, user_id=user_id):
        return False

    for child in session.scalars(select(Child).where(Child.guardian_id == user_id)):
        child.first_name = "Removed"
        child.medical_notes = None
        child.emergency_contact_name = None
        child.emergency_contact_phone = None

    session.flush()
    audit_service.record(
        session,
        action="identity.account_deleted",
        actor_id=actor_id,
        entity_type="user_account",
        entity_id=str(user_id),
        detail={"self_service": actor_id == user_id},
    )
    return True


def list_children(session: Session, guardian_id: uuid.UUID) -> list[Child]:
    """Every child the user can act for — their own plus any co-guardian's."""
    family = family_guardian_ids(session, guardian_id)
    return list(
        session.scalars(
            select(Child).where(Child.guardian_id.in_(family)).order_by(Child.created_at)
        )
    )


# --- co-guardians (PRD §7.3, "multiple guardians per family") ----------------


def family_guardian_ids(session: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    """The user plus every accepted co-guardian (link is symmetric once accepted)."""
    ids = {user_id}
    rows = session.execute(
        select(GuardianLink.guardian_id, GuardianLink.member_id).where(
            GuardianLink.accepted.is_(True),
            or_(GuardianLink.guardian_id == user_id, GuardianLink.member_id == user_id),
        )
    ).all()
    for guardian_id, member_id in rows:
        ids.add(guardian_id)
        ids.add(member_id)
    return ids


def invite_co_guardian(
    session: Session, *, owner_id: uuid.UUID, email: str
) -> GuardianLink:
    invitee = session.scalar(select(UserAccount).where(UserAccount.email == email))
    if invitee is None:
        raise CoGuardianNotFound(email)
    if invitee.id == owner_id:
        raise CannotLinkSelf(str(owner_id))
    existing = session.scalar(
        select(GuardianLink).where(
            or_(
                (GuardianLink.guardian_id == owner_id)
                & (GuardianLink.member_id == invitee.id),
                (GuardianLink.guardian_id == invitee.id)
                & (GuardianLink.member_id == owner_id),
            )
        )
    )
    if existing is not None:
        raise AlreadyLinked(email)
    link = GuardianLink(guardian_id=owner_id, member_id=invitee.id, accepted=False)
    session.add(link)
    session.flush()
    return link


def accept_co_guardian(
    session: Session, *, user_id: uuid.UUID, link_id: uuid.UUID
) -> GuardianLink:
    link = session.get(GuardianLink, link_id)
    if link is None or link.member_id != user_id:
        raise LinkNotFound(str(link_id))
    link.accepted = True
    session.flush()
    return link


def remove_co_guardian(
    session: Session, *, user_id: uuid.UUID, link_id: uuid.UUID
) -> None:
    link = session.get(GuardianLink, link_id)
    if link is None or user_id not in (link.guardian_id, link.member_id):
        raise LinkNotFound(str(link_id))
    session.delete(link)
    session.flush()


def list_co_guardians(session: Session, user_id: uuid.UUID) -> list[CoGuardianOut]:
    links = session.scalars(
        select(GuardianLink)
        .where(or_(GuardianLink.guardian_id == user_id, GuardianLink.member_id == user_id))
        .order_by(GuardianLink.created_at)
    ).all()
    out: list[CoGuardianOut] = []
    for link in links:
        sent = link.guardian_id == user_id
        other_id = link.member_id if sent else link.guardian_id
        other = session.get(UserAccount, other_id)
        out.append(
            CoGuardianOut(
                id=link.id,
                other_email=other.email if other is not None else "",
                other_name=other.full_name if other is not None else None,
                direction="sent" if sent else "received",
                accepted=link.accepted,
            )
        )
    return out
