"""Request-to-quote parties (Milestone C — PRD §9, ADR-0009).

A parent sends a **structured brief**; the provider replies with a **priced quote**; the parent
may ask for **one** revision; accepting takes the deposit and books the date.

The load-bearing design decision (see ``docs/PLANS/milestone-C-request-to-quote.md``): a quote is
a **bespoke, unlisted ``PartyPackage`` + one ``PartySlot``**. Accepting therefore calls the
existing, unchanged ``book_slot`` — the deposit (ADR-0007), the T-7d balance (ADR-0008), payout
accrual, refund clawback (ADR-0010/INV-5) and the GST tax invoice all work with **no new money
code**, and INV-1's capacity-1 guarantee on the slot is the same one instant-book relies on.

Negotiation is capped at one round by ADR-0009 — a bounded counter-offer, never a chat (EXT-1 §10).
INV-3: a brief describes the party by kid count and an age band; there is no field for a child's
name or birth date, and none of it reaches analytics.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.config.core import service as config_service
from juggle.modules.identity.core import service as identity_service
from juggle.modules.notifications.core import service as notifications_service
from juggle.modules.notifications.core.gateway import EmailGateway
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core import service as parties_service
from juggle.modules.parties.core.models import (
    PartyBooking,
    PartyPackage,
    PartyQuote,
    PartyQuoteRequest,
    PartySlot,
    PartySlotStatus,
    QuoteRequestStatus,
    QuoteStatus,
)
from juggle.modules.parties.core.schemas import QuoteIn, QuoteRequestIn
from juggle.modules.payments.core.gateway import PaymentGateway, PaymentIntentResult

# A quote that has been settled one way or another and can no longer move.
_TERMINAL = frozenset(
    {QuoteStatus.accepted, QuoteStatus.expired, QuoteStatus.withdrawn}
)


class QuoteRequestNotFound(Exception):
    """No such brief (or it isn't the caller's)."""


class QuoteNotFound(Exception):
    """No such quote (or it isn't the caller's)."""


class QuoteNotOpen(Exception):
    """The quote has already been accepted, withdrawn, or has expired."""


class RevisionLimitReached(Exception):
    """ADR-0009 allows exactly one revision round — no haggling loop."""


class RevisionNotRequested(Exception):
    """A provider may only revise after the parent has asked for a revision."""


class RequestNotOpen(Exception):
    """The brief has already been quoted, withdrawn, or closed."""


class OrganisationNotBookable(Exception):
    """The provider isn't approved, so it can't take enquiries."""


def _now() -> datetime:
    return datetime.now(UTC)


def _require_member(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    if org_service.get_member(db, org_id, actor_id) is None:
        raise parties_service.NotOrgMember(str(org_id))


def _provider_emails(db: Session, org_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    """Every member of the provider org — an enquiry that reaches nobody is a lost booking."""
    out: list[tuple[uuid.UUID, str]] = []
    for member in org_service.list_members(db, org_id):
        user = identity_service.get_user(db, member.user_account_id)
        if user is not None:
            out.append((user.id, user.email))
    return out


# --- Parent: the brief -------------------------------------------------------


def create_request(
    db: Session, *, guardian_id: uuid.UUID, data: QuoteRequestIn,
    email_gateway: EmailGateway | None = None,
) -> PartyQuoteRequest:
    """Send a brief to one provider. Only approved providers can receive enquiries."""
    org = org_service.get_organisation(db, data.organisation_id)
    if org is None or org.status.value != "approved":
        raise OrganisationNotBookable(str(data.organisation_id))

    request = PartyQuoteRequest(
        guardian_id=guardian_id,
        organisation_id=data.organisation_id,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        suburb=data.suburb,
        kid_count=data.kid_count,
        child_age_min=data.child_age_min,
        child_age_max=data.child_age_max,
        budget_cents=data.budget_cents,
        notes=data.notes,
        status=QuoteRequestStatus.submitted,
    )
    db.add(request)
    db.flush()

    if email_gateway is not None:
        when = request.starts_at.date().isoformat()
        for user_id, email in _provider_emails(db, data.organisation_id):
            notifications_service.notify_quote_requested(
                db, user_id=user_id, to_email=email, when=when,
                kid_count=request.kid_count, gateway=email_gateway,
            )
    return request


def get_request(db: Session, request_id: uuid.UUID) -> PartyQuoteRequest | None:
    return db.get(PartyQuoteRequest, request_id)


def list_guardian_requests(db: Session, guardian_id: uuid.UUID) -> list[PartyQuoteRequest]:
    return list(
        db.scalars(
            select(PartyQuoteRequest)
            .where(PartyQuoteRequest.guardian_id == guardian_id)
            .order_by(PartyQuoteRequest.created_at.desc())
        )
    )


def list_org_requests(
    db: Session, *, organisation_id: uuid.UUID, actor_id: uuid.UUID
) -> list[PartyQuoteRequest]:
    """The provider's enquiry inbox (member-gated)."""
    _require_member(db, organisation_id, actor_id)
    return list(
        db.scalars(
            select(PartyQuoteRequest)
            .where(PartyQuoteRequest.organisation_id == organisation_id)
            .order_by(PartyQuoteRequest.created_at.desc())
        )
    )


def live_quote(db: Session, request_id: uuid.UUID) -> PartyQuote | None:
    """The one quote still in play for a brief (the partial UNIQUE guarantees at most one)."""
    return db.scalar(
        select(PartyQuote).where(
            PartyQuote.request_id == request_id,
            PartyQuote.status.not_in([QuoteStatus.withdrawn, QuoteStatus.expired]),
        )
    )


def withdraw_request(
    db: Session, *, request_id: uuid.UUID, guardian_id: uuid.UUID
) -> PartyQuoteRequest:
    """The parent pulls their brief. Any live quote goes with it."""
    request = db.get(PartyQuoteRequest, request_id)
    if request is None or request.guardian_id != guardian_id:
        raise QuoteRequestNotFound(str(request_id))
    if request.status in (QuoteRequestStatus.accepted, QuoteRequestStatus.withdrawn):
        raise RequestNotOpen(request.status.value)
    quote = live_quote(db, request_id)
    if quote is not None:
        quote.status = QuoteStatus.withdrawn
        _release_offer(db, quote)
    request.status = QuoteRequestStatus.withdrawn
    db.flush()
    return request


# --- Provider: quoting -------------------------------------------------------


def _bespoke_offer(
    db: Session, *, request: PartyQuoteRequest, actor_id: uuid.UUID, data: QuoteIn
) -> tuple[PartyPackage, PartySlot]:
    """Materialise the offer as a private package + one slot.

    This is what makes the accept path free of new money code: what the parent accepts is an
    ordinary bookable package, so every downstream money path treats it like any other party.
    """
    venue = catalog_service.get_venue(db, data.venue_id)
    if venue is None or venue.organisation_id != request.organisation_id:
        raise parties_service.VenueNotFound(str(data.venue_id))
    org = org_service.get_organisation(db, request.organisation_id)
    package = PartyPackage(
        organisation_id=request.organisation_id,
        venue_id=data.venue_id,
        name=f"Bespoke party — {org.name if org else 'quote'}",
        description=data.message,
        per_head_price_cents=data.per_head_price_cents,
        # A quote is for an agreed headcount, so the band is exact — the parent can't silently
        # scale a bespoke price up or down at booking time.
        min_headcount=data.headcount,
        max_headcount=data.headcount,
        deposit_pct=data.deposit_pct,
        outdoor=False,
        quote_only=True,
    )
    db.add(package)
    db.flush()
    slot = PartySlot(
        package_id=package.id, starts_at=data.starts_at, ends_at=data.ends_at,
        status=PartySlotStatus.available,
    )
    db.add(slot)
    db.flush()
    return package, slot


def _release_offer(db: Session, quote: PartyQuote) -> None:
    """Retire the bespoke slot behind a dead quote so it can never be booked later.

    Only ever touches an ``available`` slot: once a booking exists the slot is held/booked and
    belongs to the money path (INV-1), which is not ours to unwind.
    """
    slot = db.get(PartySlot, quote.slot_id)
    if slot is not None and slot.status is PartySlotStatus.available:
        slot.status = PartySlotStatus.cancelled
    db.flush()


def send_quote(
    db: Session, *, request_id: uuid.UUID, actor_id: uuid.UUID, data: QuoteIn,
    now: datetime | None = None, email_gateway: EmailGateway | None = None,
) -> PartyQuote:
    """The provider's first offer against a brief."""
    now = now or _now()
    request = db.get(PartyQuoteRequest, request_id)
    if request is None:
        raise QuoteRequestNotFound(str(request_id))
    _require_member(db, request.organisation_id, actor_id)
    if request.status is not QuoteRequestStatus.submitted:
        raise RequestNotOpen(request.status.value)

    package, slot = _bespoke_offer(db, request=request, actor_id=actor_id, data=data)
    quote = PartyQuote(
        request_id=request.id,
        organisation_id=request.organisation_id,
        package_id=package.id,
        slot_id=slot.id,
        headcount=data.headcount,
        per_head_price_cents=data.per_head_price_cents,
        total_cents=data.per_head_price_cents * data.headcount,
        message=data.message,
        expires_at=now + timedelta(hours=config_service.party_quote_expiry_hours(db)),
        status=QuoteStatus.sent,
    )
    db.add(quote)
    # The partial UNIQUE (one live quote per brief) is the backstop against a double-submit.
    savepoint = db.begin_nested()
    try:
        db.flush()
    except IntegrityError as exc:
        savepoint.rollback()
        raise RequestNotOpen("a live quote already exists") from exc

    request.status = QuoteRequestStatus.quoted
    db.flush()
    _notify_parent_of_quote(db, request, quote, revised=False, email_gateway=email_gateway)
    return quote


def _notify_parent_of_quote(
    db: Session, request: PartyQuoteRequest, quote: PartyQuote, *, revised: bool,
    email_gateway: EmailGateway | None,
) -> None:
    if email_gateway is None:
        return
    guardian = identity_service.get_user(db, request.guardian_id)
    org = org_service.get_organisation(db, request.organisation_id)
    if guardian is None:
        return
    notifications_service.notify_quote_received(
        db, user_id=guardian.id, to_email=guardian.email,
        organisation_name=org.name if org else "the provider",
        total_cents=quote.total_cents,
        expires_at=quote.expires_at.date().isoformat(),
        revised=revised, gateway=email_gateway,
    )


def request_revision(
    db: Session, *, quote_id: uuid.UUID, guardian_id: uuid.UUID, message: str,
    now: datetime | None = None, email_gateway: EmailGateway | None = None,
) -> PartyQuote:
    """The parent's single counter-offer (ADR-0009). One round, then accept or let it lapse."""
    now = now or _now()
    quote = db.get(PartyQuote, quote_id)
    if quote is None:
        raise QuoteNotFound(str(quote_id))
    request = db.get(PartyQuoteRequest, quote.request_id)
    if request is None or request.guardian_id != guardian_id:
        raise QuoteNotFound(str(quote_id))
    if quote.status in _TERMINAL or quote.expires_at <= now:
        raise QuoteNotOpen(quote.status.value)
    # One round means one *ask*: already-asked or already-revised both block a second bite.
    if quote.revision_count >= 1 or quote.status is QuoteStatus.revision_requested:
        raise RevisionLimitReached(str(quote_id))

    quote.revision_message = message
    quote.status = QuoteStatus.revision_requested
    db.flush()

    if email_gateway is not None:
        for user_id, email in _provider_emails(db, quote.organisation_id):
            notifications_service.notify_quote_revision_requested(
                db, user_id=user_id, to_email=email, message=message, gateway=email_gateway,
            )
    return quote


def revise_quote(
    db: Session, *, quote_id: uuid.UUID, actor_id: uuid.UUID, data: QuoteIn,
    now: datetime | None = None, email_gateway: EmailGateway | None = None,
) -> PartyQuote:
    """The provider's one revised offer, in reply to the parent's ask.

    The revision replaces the bespoke package/slot (price, time or venue may all have moved)
    and the old slot is retired so it can't be booked out from under the new one.
    """
    now = now or _now()
    quote = db.get(PartyQuote, quote_id)
    if quote is None:
        raise QuoteNotFound(str(quote_id))
    _require_member(db, quote.organisation_id, actor_id)
    if quote.status is not QuoteStatus.revision_requested:
        raise RevisionNotRequested(quote.status.value)
    if quote.revision_count >= 1:
        raise RevisionLimitReached(str(quote_id))
    request = db.get(PartyQuoteRequest, quote.request_id)
    if request is None:
        raise QuoteRequestNotFound(str(quote.request_id))

    _release_offer(db, quote)  # retire the superseded slot
    package, slot = _bespoke_offer(db, request=request, actor_id=actor_id, data=data)
    quote.package_id = package.id
    quote.slot_id = slot.id
    quote.headcount = data.headcount
    quote.per_head_price_cents = data.per_head_price_cents
    quote.total_cents = data.per_head_price_cents * data.headcount
    quote.message = data.message
    quote.revision_count += 1
    quote.status = QuoteStatus.revised
    # A revised quote gets a fresh window — the parent shouldn't inherit a nearly-dead clock.
    quote.expires_at = now + timedelta(hours=config_service.party_quote_expiry_hours(db))
    db.flush()
    _notify_parent_of_quote(db, request, quote, revised=True, email_gateway=email_gateway)
    return quote


def withdraw_quote(
    db: Session, *, quote_id: uuid.UUID, actor_id: uuid.UUID,
    email_gateway: EmailGateway | None = None,
) -> PartyQuote:
    """The provider pulls an unaccepted offer."""
    quote = db.get(PartyQuote, quote_id)
    if quote is None:
        raise QuoteNotFound(str(quote_id))
    _require_member(db, quote.organisation_id, actor_id)
    if quote.status in _TERMINAL:
        raise QuoteNotOpen(quote.status.value)
    quote.status = QuoteStatus.withdrawn
    _release_offer(db, quote)
    request = db.get(PartyQuoteRequest, quote.request_id)
    if request is not None:
        request.status = QuoteRequestStatus.submitted  # open again; they may re-quote
    db.flush()
    _notify_parent_closed(db, quote, reason="withdrawn", email_gateway=email_gateway)
    return quote


def decline_request(
    db: Session, *, request_id: uuid.UUID, actor_id: uuid.UUID,
    email_gateway: EmailGateway | None = None,
) -> PartyQuoteRequest:
    """The provider passes on a brief without quoting."""
    request = db.get(PartyQuoteRequest, request_id)
    if request is None:
        raise QuoteRequestNotFound(str(request_id))
    _require_member(db, request.organisation_id, actor_id)
    if request.status is not QuoteRequestStatus.submitted:
        raise RequestNotOpen(request.status.value)
    request.status = QuoteRequestStatus.declined
    db.flush()
    if email_gateway is not None:
        guardian = identity_service.get_user(db, request.guardian_id)
        org = org_service.get_organisation(db, request.organisation_id)
        if guardian is not None:
            notifications_service.notify_quote_closed(
                db, user_id=guardian.id, to_email=guardian.email,
                organisation_name=org.name if org else "the provider",
                reason="declined", gateway=email_gateway,
            )
    return request


def _notify_parent_closed(
    db: Session, quote: PartyQuote, *, reason: str, email_gateway: EmailGateway | None
) -> None:
    if email_gateway is None:
        return
    request = db.get(PartyQuoteRequest, quote.request_id)
    if request is None:
        return
    guardian = identity_service.get_user(db, request.guardian_id)
    org = org_service.get_organisation(db, quote.organisation_id)
    if guardian is None:
        return
    notifications_service.notify_quote_closed(
        db, user_id=guardian.id, to_email=guardian.email,
        organisation_name=org.name if org else "the provider",
        reason=reason, gateway=email_gateway,
    )


# --- Parent: accepting (hands over to the existing deposit rails) ------------


def accept_quote(
    db: Session, *, quote_id: uuid.UUID, guardian_id: uuid.UUID, gateway: PaymentGateway,
    now: datetime | None = None, email_gateway: EmailGateway | None = None,
) -> tuple[PartyQuote, PartyBooking, PaymentIntentResult]:
    """Accept a live quote: books its bespoke slot through the unchanged ``book_slot``.

    Everything about the money — deposit %, the PaymentIntent, the T-7d balance, the payout and
    any later refund — is the instant-book path, untouched (INV-2). All this layer does is decide
    that the offer is still live and hand over.
    """
    now = now or _now()
    quote = db.get(PartyQuote, quote_id)
    if quote is None:
        raise QuoteNotFound(str(quote_id))
    request = db.get(PartyQuoteRequest, quote.request_id)
    if request is None or request.guardian_id != guardian_id:
        raise QuoteNotFound(str(quote_id))
    if quote.status in _TERMINAL:
        raise QuoteNotOpen(quote.status.value)
    if quote.expires_at <= now:
        # Don't book a lapsed price; the sweep will formalise the expiry.
        raise QuoteNotOpen("expired")

    booking, intent = parties_service.book_slot(
        db, slot_id=quote.slot_id, guardian_id=guardian_id,
        headcount=quote.headcount, gateway=gateway,
    )
    quote.status = QuoteStatus.accepted
    quote.booking_id = booking.id
    request.status = QuoteRequestStatus.accepted
    db.flush()

    if email_gateway is not None:
        for user_id, email in _provider_emails(db, quote.organisation_id):
            notifications_service.notify_quote_accepted(
                db, user_id=user_id, to_email=email,
                when=request.starts_at.date().isoformat(),
                total_cents=quote.total_cents, gateway=email_gateway,
            )
    return quote, booking, intent


# --- Expiry sweep (scheduler tick) ------------------------------------------


def expire_due_quotes(
    db: Session, *, now: datetime | None = None, email_gateway: EmailGateway | None = None
) -> int:
    """Expire quotes past their window. Idempotent — a second pass finds nothing.

    Accepted quotes are never touched: the money has moved and the slot is booked.
    """
    now = now or _now()
    due = list(
        db.scalars(
            select(PartyQuote).where(
                PartyQuote.expires_at <= now,
                PartyQuote.status.not_in(list(_TERMINAL)),
            )
        )
    )
    for quote in due:
        quote.status = QuoteStatus.expired
        _release_offer(db, quote)
        request = db.get(PartyQuoteRequest, quote.request_id)
        if request is not None and request.status is QuoteRequestStatus.quoted:
            request.status = QuoteRequestStatus.expired
        _notify_parent_closed(db, quote, reason="expired", email_gateway=email_gateway)
    db.flush()
    return len(due)
