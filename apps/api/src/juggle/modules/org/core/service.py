"""Business logic for the org module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).

Note the module boundary: this service never imports the identity module. It
references users only by ``user_account_id`` (a foreign key); a bad id surfaces
as ``UnknownUser`` via the DB constraint rather than an in-process lookup.
"""

import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.events.core import service as events_service
from juggle.modules.org.core.models import (
    InsuranceDoc,
    Organisation,
    OrgMember,
    OrgRole,
    OrgStatus,
    VerificationStatus,
    WwccRecord,
)

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
    events_service.record(
        session, event_type="provider_signup", props={"organisation_id": str(org.id)}
    )
    return org


def get_organisation(session: Session, org_id: uuid.UUID) -> Organisation | None:
    return session.get(Organisation, org_id)


def get_org_by_stripe_account(session: Session, account_id: str) -> Organisation | None:
    """Reverse-lookup used by the payments ``account.updated`` webhook (F-PAY-1)."""
    return session.scalar(
        select(Organisation).where(Organisation.stripe_account_id == account_id)
    )


def set_stripe_account(
    session: Session, org_id: uuid.UUID, account_id: str
) -> Organisation | None:
    """Attach a newly created Stripe Connect account to the org (payments onboarding)."""
    org = session.get(Organisation, org_id)
    if org is None:
        return None
    org.stripe_account_id = account_id
    session.flush()
    return org


def set_connect_flags(
    session: Session,
    org_id: uuid.UUID,
    *,
    charges_enabled: bool,
    payouts_enabled: bool,
) -> Organisation | None:
    """Mirror Stripe's capability flags onto the org (payments onboarding / webhook)."""
    org = session.get(Organisation, org_id)
    if org is None:
        return None
    org.charges_enabled = charges_enabled
    org.payouts_enabled = payouts_enabled
    session.flush()
    return org


def expire_due_compliance(session: Session, *, today: date) -> int:
    """Transition WWCC/insurance whose expiry has passed to ``expired`` (PRD §8.1
    expiry tracking) — so a lapsed check no longer counts as verified. Returns the
    number of records expired. Driven by the scheduler each tick."""
    stale = (VerificationStatus.pending, VerificationStatus.verified)
    count = 0
    for record in session.scalars(
        select(WwccRecord).where(
            WwccRecord.expiry_date < today, WwccRecord.status.in_(stale)
        )
    ):
        record.status = VerificationStatus.expired
        count += 1
    for doc in session.scalars(
        select(InsuranceDoc).where(
            InsuranceDoc.expiry_date.is_not(None),
            InsuranceDoc.expiry_date < today,
            InsuranceDoc.status.in_(stale),
        )
    ):
        doc.status = VerificationStatus.expired
        count += 1
    if count:
        session.flush()
    return count


def verification_badges(session: Session, org_id: uuid.UUID) -> dict[str, bool]:
    """Public trust signals for a provider (PRD §7.2): approved by ops, ABN on
    file, and at least one *verified* WWCC / insurance record."""
    org = session.get(Organisation, org_id)
    if org is None:
        return {
            "approved": False,
            "abn_on_file": False,
            "wwcc_verified": False,
            "insurance_verified": False,
        }
    wwcc_verified = (
        session.scalar(
            select(WwccRecord.id).where(
                WwccRecord.organisation_id == org_id,
                WwccRecord.status == VerificationStatus.verified,
            )
        )
        is not None
    )
    insurance_verified = (
        session.scalar(
            select(InsuranceDoc.id).where(
                InsuranceDoc.organisation_id == org_id,
                InsuranceDoc.status == VerificationStatus.verified,
            )
        )
        is not None
    )
    return {
        "approved": org.status is OrgStatus.approved,
        "abn_on_file": bool(org.abn),
        "wwcc_verified": wwcc_verified,
        "insurance_verified": insurance_verified,
    }


def list_user_orgs(session: Session, user_id: uuid.UUID) -> list[Organisation]:
    """Organisations the user is a member of (their provider dashboard)."""
    return list(
        session.scalars(
            select(Organisation)
            .join(OrgMember, OrgMember.organisation_id == Organisation.id)
            .where(OrgMember.user_account_id == user_id)
            .order_by(Organisation.created_at)
        )
    )


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


# --- Onboarding & verification (PRD §8.1, §11) -----------------------------

def set_abn(session: Session, org_id: uuid.UUID, abn: str) -> Organisation | None:
    org = session.get(Organisation, org_id)
    if org is None:
        return None
    org.abn = abn
    session.flush()
    return org


def add_wwcc(
    session: Session,
    *,
    org_id: uuid.UUID,
    staff_name: str,
    wwcc_number: str,
    expiry_date: date,
) -> WwccRecord:
    record = WwccRecord(
        organisation_id=org_id,
        staff_name=staff_name,
        wwcc_number=wwcc_number,
        expiry_date=expiry_date,
    )
    session.add(record)
    session.flush()
    return record


def list_wwcc(session: Session, org_id: uuid.UUID) -> list[WwccRecord]:
    return list(
        session.scalars(
            select(WwccRecord)
            .where(WwccRecord.organisation_id == org_id)
            .order_by(WwccRecord.created_at)
        )
    )


def add_insurance(
    session: Session,
    *,
    org_id: uuid.UUID,
    file_ref: str,
    expiry_date: date | None = None,
) -> InsuranceDoc:
    doc = InsuranceDoc(organisation_id=org_id, file_ref=file_ref, expiry_date=expiry_date)
    session.add(doc)
    session.flush()
    return doc


def list_insurance(session: Session, org_id: uuid.UUID) -> list[InsuranceDoc]:
    return list(
        session.scalars(
            select(InsuranceDoc)
            .where(InsuranceDoc.organisation_id == org_id)
            .order_by(InsuranceDoc.created_at)
        )
    )


def set_wwcc_status(
    session: Session, wwcc_id: uuid.UUID, status: VerificationStatus
) -> WwccRecord | None:
    record = session.get(WwccRecord, wwcc_id)
    if record is None:
        return None
    record.status = status
    session.flush()
    return record


def set_insurance_status(
    session: Session, insurance_id: uuid.UUID, status: VerificationStatus
) -> InsuranceDoc | None:
    doc = session.get(InsuranceDoc, insurance_id)
    if doc is None:
        return None
    doc.status = status
    session.flush()
    return doc


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
