"""Admin service: the operator's levers (PRD §10). Top of the layering, so it
composes org / booking / identity / config / audit through their services.

Impersonation (PRD §10.3) issues a scoped, time-boxed token that carries both
the target (``sub``) and the true actor (``impersonator_id``); every start/end is
audited, and per-action audit happens in the auth dependency.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.admin.core.models import ImpersonationMode, ImpersonationSession
from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core import service as booking_service
from juggle.modules.booking.core.schemas import OrderOut
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import UserAccount
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import (
    InsuranceDoc,
    Organisation,
    OrgStatus,
    VerificationStatus,
    WwccRecord,
)
from juggle.modules.payments.core.gateway import PaymentGateway
from juggle.security import create_impersonation_token


class OrgNotFound(Exception):
    """No such organisation."""


class PaymentNotFound(Exception):
    """No such payment."""


class TargetNotFound(Exception):
    """Impersonation target user does not exist."""


class CannotImpersonate(Exception):
    """Target may not be impersonated (self, or another admin)."""


class ImpersonationNotFound(Exception):
    """No such impersonation session."""


class VerificationNotFound(Exception):
    """No such WWCC / insurance record."""


class InvalidMode(Exception):
    """Impersonation mode must be 'view_as' or 'act_as'."""


# --- Provider approval / verification (PRD §10.2) --------------------------

def list_orgs(db: Session, status: OrgStatus) -> list[Organisation]:
    return org_service.list_by_status(db, status)


def find_users(db: Session, query: str) -> list[UserAccount]:
    """Support lookup by email/name (PRD §10.2)."""
    return identity_service.search_users(db, query=query)


def _set_org_status(
    db: Session, *, org_id: uuid.UUID, status: OrgStatus, actor_id: uuid.UUID, action: str
) -> Organisation:
    org = org_service.set_status(db, org_id, status)
    if org is None:
        raise OrgNotFound(str(org_id))
    audit_service.record(
        db,
        action=action,
        actor_id=actor_id,
        entity_type="organisation",
        entity_id=str(org_id),
        detail={"status": status.value},
    )
    return org


def approve_org(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID) -> Organisation:
    return _set_org_status(
        db, org_id=org_id, status=OrgStatus.approved, actor_id=actor_id, action="admin.org.approve"
    )


def suspend_org(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID) -> Organisation:
    return _set_org_status(
        db, org_id=org_id, status=OrgStatus.suspended, actor_id=actor_id, action="admin.org.suspend"
    )


def get_org_verifications(
    db: Session, org_id: uuid.UUID
) -> tuple[Organisation, list[WwccRecord], list[InsuranceDoc]]:
    org = org_service.get_organisation(db, org_id)
    if org is None:
        raise OrgNotFound(str(org_id))
    return org, org_service.list_wwcc(db, org_id), org_service.list_insurance(db, org_id)


def verify_wwcc(
    db: Session, *, wwcc_id: uuid.UUID, status: VerificationStatus, actor_id: uuid.UUID
) -> WwccRecord:
    record = org_service.set_wwcc_status(db, wwcc_id, status)
    if record is None:
        raise VerificationNotFound(str(wwcc_id))
    audit_service.record(
        db,
        action="admin.wwcc.verify",
        actor_id=actor_id,
        entity_type="wwcc_record",
        entity_id=str(wwcc_id),
        detail={"status": status.value},
    )
    return record


def verify_insurance(
    db: Session, *, insurance_id: uuid.UUID, status: VerificationStatus, actor_id: uuid.UUID
) -> InsuranceDoc:
    doc = org_service.set_insurance_status(db, insurance_id, status)
    if doc is None:
        raise VerificationNotFound(str(insurance_id))
    audit_service.record(
        db,
        action="admin.insurance.verify",
        actor_id=actor_id,
        entity_type="insurance_doc",
        entity_id=str(insurance_id),
        detail={"status": status.value},
    )
    return doc


# --- Bookings console (PRD §10.2) ------------------------------------------

def refund_payment(
    db: Session,
    *,
    payment_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    gateway: PaymentGateway,
) -> OrderOut:
    try:
        order = booking_service.refund_order(db, payment_id=payment_id, gateway=gateway)
    except booking_service.PaymentNotFound as exc:
        raise PaymentNotFound(str(payment_id)) from exc
    audit_service.record(
        db,
        action="admin.payment.refund",
        actor_id=actor_id,
        entity_type="payment",
        entity_id=str(payment_id),
        detail={"reason": reason},
    )
    return order


# --- Impersonation (PRD §10.3) ---------------------------------------------

def start_impersonation(
    db: Session,
    *,
    impersonator_id: uuid.UUID,
    target_user_id: uuid.UUID,
    mode: str,
    reason: str | None,
) -> tuple[ImpersonationSession, str]:
    try:
        mode_enum = ImpersonationMode(mode)
    except ValueError as exc:
        raise InvalidMode(mode) from exc

    target = identity_service.get_user(db, target_user_id)
    if target is None:
        raise TargetNotFound(str(target_user_id))
    if target.id == impersonator_id or target.is_admin:
        raise CannotImpersonate(str(target_user_id))

    ttl_minutes = config_service.impersonation_ttl_minutes(db)
    session_row = ImpersonationSession(
        impersonator_id=impersonator_id,
        target_id=target.id,
        mode=mode_enum,
        reason=reason,
        expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    )
    db.add(session_row)
    db.flush()

    token = create_impersonation_token(
        target_id=target.id,
        impersonator_id=impersonator_id,
        mode=mode_enum.value,
        session_id=session_row.id,
        ttl_minutes=ttl_minutes,
    )
    audit_service.record(
        db,
        action="impersonation.start",
        actor_id=impersonator_id,
        impersonated_id=target.id,
        entity_type="impersonation_session",
        entity_id=str(session_row.id),
        detail={"mode": mode_enum.value, "reason": reason},
    )
    return session_row, token


def end_impersonation(
    db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID
) -> ImpersonationSession:
    session_row = db.get(ImpersonationSession, session_id)
    if session_row is None:
        raise ImpersonationNotFound(str(session_id))
    if session_row.ended_at is None:
        session_row.ended_at = datetime.now(UTC)
        db.flush()
        audit_service.record(
            db,
            action="impersonation.end",
            actor_id=actor_id,
            impersonated_id=session_row.target_id,
            entity_type="impersonation_session",
            entity_id=str(session_id),
        )
    return session_row


def list_active_impersonations(db: Session) -> list[ImpersonationSession]:
    now = datetime.now(UTC)
    return list(
        db.scalars(
            select(ImpersonationSession)
            .where(
                ImpersonationSession.ended_at.is_(None),
                ImpersonationSession.expires_at > now,
            )
            .order_by(ImpersonationSession.created_at.desc())
        )
    )
