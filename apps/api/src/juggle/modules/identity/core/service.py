"""Business logic for the identity module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.identity.core.models import (
    Child,
    GuardianLink,
    UserAccount,
    UserStatus,
)
from juggle.modules.identity.core.schemas import ChildCreate, CoGuardianOut
from juggle.security import hash_password, verify_password


class EmailAlreadyExists(Exception):
    """Raised when signing up with an email that is already registered."""


class CoGuardianNotFound(Exception):
    """No account with that email to invite as a co-guardian."""


class CannotLinkSelf(Exception):
    """A guardian cannot add themselves as a co-guardian."""


class AlreadyLinked(Exception):
    """These two accounts already have a co-guardian link."""


class LinkNotFound(Exception):
    """No such co-guardian link for this user."""


def create_guardian(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    phone: str | None = None,
) -> UserAccount:
    if session.scalar(select(UserAccount).where(UserAccount.email == email)) is not None:
        raise EmailAlreadyExists(email)
    user = UserAccount(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
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
