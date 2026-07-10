"""Business logic for the org module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).

Note the module boundary: this service never imports the identity module. It
references users only by ``user_account_id`` (a foreign key); a bad id surfaces
as ``UnknownUser`` via the DB constraint rather than an in-process lookup.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.org.core.models import Organisation, OrgMember, OrgRole, OrgStatus

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


class DuplicateMember(Exception):
    """The user is already a member of the organisation."""


class UnknownUser(Exception):
    """The referenced user_account_id does not exist."""


def _slugify(name: str) -> str:
    base = _SLUG_STRIP.sub("-", name.lower()).strip("-") or "org"
    # A short suffix keeps slugs unique without a lookup/retry loop.
    return f"{base[:40]}-{uuid.uuid4().hex[:6]}"


def create_organisation(
    session: Session, *, name: str, owner_user_id: uuid.UUID
) -> Organisation:
    org = Organisation(name=name, slug=_slugify(name))
    session.add(org)
    session.flush()
    session.add(
        OrgMember(organisation_id=org.id, user_account_id=owner_user_id, role=OrgRole.owner)
    )
    session.flush()
    return org


def get_organisation(session: Session, org_id: uuid.UUID) -> Organisation | None:
    return session.get(Organisation, org_id)


def set_status(session: Session, org_id: uuid.UUID, status: OrgStatus) -> Organisation | None:
    """Admin lifecycle transition (approve / suspend / reinstate)."""
    org = session.get(Organisation, org_id)
    if org is None:
        return None
    org.status = status
    session.flush()
    return org


def list_by_status(session: Session, status: OrgStatus) -> list[Organisation]:
    return list(
        session.scalars(
            select(Organisation)
            .where(Organisation.status == status)
            .order_by(Organisation.created_at)
        )
    )


def adjust_reliability(
    session: Session, org_id: uuid.UUID, delta: float
) -> Organisation | None:
    """Nudge an org's reliability score, clamped to [0, 1] (PRD §8.3)."""
    org = session.get(Organisation, org_id)
    if org is None:
        return None
    org.reliability_score = max(0.0, min(1.0, org.reliability_score + delta))
    session.flush()
    return org


def get_member(
    session: Session, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMember | None:
    return session.scalar(
        select(OrgMember).where(
            OrgMember.organisation_id == org_id,
            OrgMember.user_account_id == user_id,
        )
    )


def list_members(session: Session, org_id: uuid.UUID) -> list[OrgMember]:
    return list(
        session.scalars(
            select(OrgMember)
            .where(OrgMember.organisation_id == org_id)
            .order_by(OrgMember.created_at)
        )
    )


def add_member(
    session: Session, *, org_id: uuid.UUID, user_account_id: uuid.UUID, role: OrgRole
) -> OrgMember:
    if get_member(session, org_id, user_account_id) is not None:
        raise DuplicateMember(str(user_account_id))
    member = OrgMember(organisation_id=org_id, user_account_id=user_account_id, role=role)
    session.add(member)
    try:
        session.flush()
    except IntegrityError as exc:
        # The only remaining FK is user_account_id → user_account.id.
        raise UnknownUser(str(user_account_id)) from exc
    return member
