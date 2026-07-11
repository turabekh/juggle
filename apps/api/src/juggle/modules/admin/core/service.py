"""Admin service: the operator's levers (PRD §10). Top of the layering, so it
composes org / booking / identity / config / audit through their services.

Impersonation (PRD §10.3) issues a scoped, time-boxed token that carries both
the target (``sub``) and the true actor (``impersonator_id``); every start/end is
audited, and per-action audit happens in the auth dependency.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from juggle.modules.admin.core.models import ImpersonationMode, ImpersonationSession
from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core import service as booking_service
from juggle.modules.booking.core.models import Booking
from juggle.modules.booking.core.schemas import BookingOut, OrderOut
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.identity.core.models import Child, GuardianLink, UserAccount
from juggle.modules.inventory.core.models import SeatHold
from juggle.modules.notifications.core.models import NotificationLog
from juggle.modules.org.core import service as org_service
from juggle.modules.org.core.models import (
    InsuranceDoc,
    Organisation,
    OrgStatus,
    VerificationStatus,
    WwccRecord,
)
from juggle.modules.payments.core import service as payments_service
from juggle.modules.payments.core.gateway import PaymentGateway
from juggle.modules.payments.core.models import Payment, Payout, PayoutStatus
from juggle.modules.qanda.core.models import ListingQuestion
from juggle.modules.reviews.core.models import Review
from juggle.modules.waitlist.core.models import ACTIVE_STATUSES, WaitlistEntry, WaitlistStatus
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


class PayoutNotFound(Exception):
    """No such payout."""


class InvalidMode(Exception):
    """Impersonation mode must be 'view_as' or 'act_as'."""


# --- Provider approval / verification (PRD §10.2) --------------------------

def list_orgs(db: Session, status: OrgStatus) -> list[Organisation]:
    return org_service.list_by_status(db, status)


def find_users(db: Session, query: str) -> list[UserAccount]:
    """Support lookup by email/name (PRD §10.2)."""
    return identity_service.search_users(db, query=query)


def user_bookings(db: Session, user_id: uuid.UUID) -> list[BookingOut]:
    """A user's booking history for support (PRD §10.2)."""
    return booking_service.list_bookings(db, user_id)


class UserNotFound(Exception):
    """No such user to delete."""


class CannotDeleteAdmin(Exception):
    """Refuse to data-delete an admin account."""


def delete_user(db: Session, *, user_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Action an APP data-deletion request (PRD §10.2). Admin accounts are
    protected; the anonymisation + audit happen in ``identity``."""
    user = db.get(UserAccount, user_id)
    if user is None:
        raise UserNotFound(str(user_id))
    if user.is_admin:
        raise CannotDeleteAdmin(str(user_id))
    identity_service.delete_account(db, user_id=user_id, actor_id=actor_id)


class CannotMergeSelf(Exception):
    """Source and target are the same account."""


def _merge_waitlist(db: Session, source_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """Move the source's waitlist entries to the target, but drop any that would
    clash with a target entry already active on the same session (partial UNIQUE)."""
    for entry in db.scalars(
        select(WaitlistEntry).where(WaitlistEntry.guardian_id == source_id)
    ):
        if entry.status in ACTIVE_STATUSES:
            clash = db.scalar(
                select(WaitlistEntry.id).where(
                    WaitlistEntry.guardian_id == target_id,
                    WaitlistEntry.session_id == entry.session_id,
                    WaitlistEntry.status.in_(ACTIVE_STATUSES),
                )
            )
            if clash is not None:
                entry.status = WaitlistStatus.cancelled  # target already queued here
                continue
        entry.guardian_id = target_id


def _merge_guardian_links(db: Session, source_id: uuid.UUID, target_id: uuid.UUID) -> None:
    """Repoint the source's co-guardian links to the target, dropping self-links
    and any that would duplicate an existing target link (UNIQUE pair)."""
    for link in db.scalars(
        select(GuardianLink).where(
            or_(GuardianLink.guardian_id == source_id, GuardianLink.member_id == source_id)
        )
    ):
        new_guardian = target_id if link.guardian_id == source_id else link.guardian_id
        new_member = target_id if link.member_id == source_id else link.member_id
        if new_guardian == new_member:
            db.delete(link)
            continue
        duplicate = db.scalar(
            select(GuardianLink.id).where(
                GuardianLink.id != link.id,
                or_(
                    (GuardianLink.guardian_id == new_guardian)
                    & (GuardianLink.member_id == new_member),
                    (GuardianLink.guardian_id == new_member)
                    & (GuardianLink.member_id == new_guardian),
                ),
            )
        )
        if duplicate is not None:
            db.delete(link)
        else:
            link.guardian_id = new_guardian
            link.member_id = new_member


def merge_accounts(
    db: Session, *, source_id: uuid.UUID, target_id: uuid.UUID, actor_id: uuid.UUID
) -> None:
    """Merge a duplicate guardian account into a primary one (PRD §10.2): move all
    of the source's family data to the target, then deactivate the source. Admin
    accounts are protected. This is an admin-owned cross-cutting data operation,
    so it reassigns lower modules' owner columns directly (like the roster reads)."""
    if source_id == target_id:
        raise CannotMergeSelf(str(source_id))
    source = db.get(UserAccount, source_id)
    target = db.get(UserAccount, target_id)
    if source is None or target is None:
        raise UserNotFound(str(source_id if source is None else target_id))
    if source.is_admin or target.is_admin:
        raise CannotDeleteAdmin("cannot merge admin accounts")

    # Simple owner-column reassignments (no uniqueness on these columns).
    reassignments = [
        update(Child).where(Child.guardian_id == source_id).values(guardian_id=target_id),
        update(Booking).where(Booking.guardian_id == source_id).values(guardian_id=target_id),
        update(Payment).where(Payment.guardian_id == source_id).values(guardian_id=target_id),
        update(SeatHold).where(SeatHold.held_by_id == source_id).values(held_by_id=target_id),
        update(Review).where(Review.author_id == source_id).values(author_id=target_id),
        update(ListingQuestion)
        .where(ListingQuestion.asker_id == source_id)
        .values(asker_id=target_id),
        update(NotificationLog)
        .where(NotificationLog.user_account_id == source_id)
        .values(user_account_id=target_id),
    ]
    for stmt in reassignments:
        db.execute(stmt)

    # Constrained tables need conflict handling.
    _merge_waitlist(db, source_id, target_id)
    _merge_guardian_links(db, source_id, target_id)
    db.flush()

    identity_service.deactivate_account(db, user_id=source_id)
    audit_service.record(
        db,
        action="admin.accounts_merged",
        actor_id=actor_id,
        entity_type="user_account",
        entity_id=str(source_id),
        detail={"merged_into": str(target_id)},
    )


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


# --- Payouts ops (PRD §8.4, §10.2) -----------------------------------------

def run_payouts(
    db: Session, *, actor_id: uuid.UUID, gateway: PaymentGateway
) -> tuple[int, int]:
    released, total = payments_service.release_due_payouts(db, gateway=gateway)
    audit_service.record(
        db,
        action="admin.payouts.run",
        actor_id=actor_id,
        entity_type="payout",
        detail={"released": released, "total_cents": total},
    )
    return released, total


def list_payouts(db: Session, status: PayoutStatus) -> list[Payout]:
    return payments_service.list_payouts_by_status(db, status)


def set_payout_hold(
    db: Session, *, payout_id: uuid.UUID, held: bool, actor_id: uuid.UUID
) -> Payout:
    new_status = PayoutStatus.held if held else PayoutStatus.scheduled
    payout = payments_service.set_payout_status(db, payout_id, new_status)
    if payout is None:
        raise PayoutNotFound(str(payout_id))
    audit_service.record(
        db,
        action="admin.payout.hold" if held else "admin.payout.release",
        actor_id=actor_id,
        entity_type="payout",
        entity_id=str(payout_id),
        detail={"status": new_status.value},
    )
    return payout


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
