"""Comms service (PRD §8.5): provider broadcasts to a session's booked families.

Sits high in the layering (above booking): it authorises via ``org`` membership,
reads the confirmed bookings for a session to find the distinct booked families,
and delivers provider-authored content through the ``notifications`` gateway —
recording one ``Broadcast`` row as the provider's outbound history. There is no
free-text parent↔provider channel (PRD §8.5); the provider composes, we fan out.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from juggle.modules.audit.core import service as audit_service
from juggle.modules.booking.core.models import Booking, BookingStatus
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.comms.core.models import Broadcast
from juggle.modules.comms.core.schemas import BroadcastOut
from juggle.modules.identity.core import service as identity_service
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway
from juggle.modules.org.core import service as org_service


class SessionNotFound(Exception):
    """No such session."""


class NotOrgMember(Exception):
    """Caller is not a member of the organisation running this session."""


class NoRecipients(Exception):
    """No confirmed families to message on this session."""


def _broadcast_out(b: Broadcast) -> BroadcastOut:
    return BroadcastOut(
        id=b.id,
        session_id=b.session_id,
        template_key=b.template_key,
        subject=b.subject,
        body=b.body,
        recipient_count=b.recipient_count,
        created_at=b.created_at,
    )


def _booked_guardian_ids(db: Session, session_id: uuid.UUID) -> list[uuid.UUID]:
    """Distinct guardians with a confirmed booking on the session."""
    return list(
        db.scalars(
            select(Booking.guardian_id)
            .where(
                Booking.session_id == session_id,
                Booking.status == BookingStatus.confirmed,
            )
            .distinct()
        )
    )


def _require_org_session(
    db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID
) -> uuid.UUID:
    """Return the org id after checking the session exists and the actor is a member."""
    session = catalog_service.get_session(db, session_id)
    if session is None:
        raise SessionNotFound(str(session_id))
    program = catalog_service.get_program(db, session.program_id)
    if program is None:
        raise SessionNotFound(str(session_id))
    if org_service.get_member(db, program.organisation_id, actor_id) is None:
        raise NotOrgMember(str(program.organisation_id))
    return program.organisation_id


def send_broadcast(
    db: Session,
    *,
    session_id: uuid.UUID,
    actor_id: uuid.UUID,
    subject: str,
    body: str,
    template_key: str | None,
    gateway: EmailGateway,
) -> BroadcastOut:
    org_id = _require_org_session(db, session_id=session_id, actor_id=actor_id)
    org = org_service.get_organisation(db, org_id)
    org_name = org.name if org is not None else "Your provider"

    guardian_ids = _booked_guardian_ids(db, session_id)
    if not guardian_ids:
        raise NoRecipients(str(session_id))

    sent = 0
    for guardian_id in guardian_ids:
        guardian = identity_service.get_user(db, guardian_id)
        if guardian is None:
            continue
        notifications_service.notify_provider_broadcast(
            db,
            user_id=guardian.id,
            to_email=guardian.email,
            organisation_name=org_name,
            subject=subject,
            body=body,
            gateway=gateway,
        )
        sent += 1

    broadcast = Broadcast(
        session_id=session_id,
        organisation_id=org_id,
        sender_id=actor_id,
        template_key=template_key,
        subject=subject,
        body=body,
        recipient_count=sent,
    )
    db.add(broadcast)
    db.flush()
    audit_service.record(
        db,
        action="comms.broadcast_sent",
        actor_id=actor_id,
        entity_type="broadcast",
        entity_id=str(broadcast.id),
        detail={"session_id": str(session_id), "recipients": sent},
    )
    return _broadcast_out(broadcast)


def list_broadcasts(
    db: Session, *, session_id: uuid.UUID, actor_id: uuid.UUID
) -> list[BroadcastOut]:
    _require_org_session(db, session_id=session_id, actor_id=actor_id)
    broadcasts = db.scalars(
        select(Broadcast)
        .where(Broadcast.session_id == session_id)
        .order_by(Broadcast.created_at.desc())
    )
    return [_broadcast_out(b) for b in broadcasts]
