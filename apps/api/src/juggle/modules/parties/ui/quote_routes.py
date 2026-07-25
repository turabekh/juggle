"""HTTP routes for request-to-quote parties (Milestone C — PRD §9, ADR-0009).

Everything is gated on the ``party_quotes`` feature flag — 404 when off. Like the party
planner, the flow is email-driven end to end (a brief nobody is told about is a dead end), so
it stays dark until a real email provider is configured.

Accepting a quote returns the same ``PartyBookingOut`` (with the deposit ``client_secret``) as
instant-book, because it *is* instant-book underneath — see ``core/quotes.py``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.catalog.core import service as catalog_service
from juggle.modules.config.core import service as config_service
from juggle.modules.flags.core import service as flags_service
from juggle.modules.notifications.core.gateway import EmailGateway, get_email_gateway
from juggle.modules.org.core import service as org_service
from juggle.modules.parties.core import quotes, schemas, service
from juggle.modules.parties.core.models import PartyQuote, PartyQuoteRequest, PartySlot
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]
EmailGatewayDep = Annotated[EmailGateway, Depends(get_email_gateway)]


def _require_flag(session: SessionDep) -> None:
    if not flags_service.is_enabled(session, "party_quotes"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


router = APIRouter(
    prefix="/parties/quotes", tags=["parties"], dependencies=[Depends(_require_flag)]
)


# --- Serialisation -----------------------------------------------------------


def _quote_detail(session: Session, quote: PartyQuote) -> schemas.QuoteDetailOut:
    slot = session.get(PartySlot, quote.slot_id)
    package = service.get_package(session, quote.package_id)
    venue = catalog_service.get_venue(session, package.venue_id) if package else None
    org = org_service.get_organisation(session, quote.organisation_id)
    deposit_pct = (
        package.deposit_pct if package and package.deposit_pct is not None
        else config_service.party_deposit_pct(session)
    )
    return schemas.QuoteDetailOut(
        id=quote.id,
        request_id=quote.request_id,
        organisation_id=quote.organisation_id,
        package_id=quote.package_id,
        slot_id=quote.slot_id,
        headcount=quote.headcount,
        per_head_price_cents=quote.per_head_price_cents,
        total_cents=quote.total_cents,
        message=quote.message,
        revision_message=quote.revision_message,
        revision_count=quote.revision_count,
        expires_at=quote.expires_at,
        booking_id=quote.booking_id,
        status=quote.status.value,
        starts_at=slot.starts_at if slot else quote.created_at,
        ends_at=slot.ends_at if slot else quote.created_at,
        venue_name=venue.name if venue else "",
        organisation_name=org.name if org else "",
        deposit_cents=round(quote.total_cents * deposit_pct / 100),
        # One round only (ADR-0009): a revision already asked for or already delivered closes it.
        can_request_revision=(
            quote.revision_count == 0
            and quote.status.value == "sent"
        ),
    )


def _request_detail(
    session: Session, request: PartyQuoteRequest
) -> schemas.QuoteRequestDetailOut:
    org = org_service.get_organisation(session, request.organisation_id)
    quote = quotes.live_quote(session, request.id)
    return schemas.QuoteRequestDetailOut(
        id=request.id,
        guardian_id=request.guardian_id,
        organisation_id=request.organisation_id,
        starts_at=request.starts_at,
        ends_at=request.ends_at,
        suburb=request.suburb,
        kid_count=request.kid_count,
        child_age_min=request.child_age_min,
        child_age_max=request.child_age_max,
        budget_cents=request.budget_cents,
        notes=request.notes,
        status=request.status.value,
        organisation_name=org.name if org else "",
        quote=_quote_detail(session, quote) if quote is not None else None,
    )


# --- Parent ------------------------------------------------------------------


@router.post(
    "/requests", status_code=status.HTTP_201_CREATED,
    response_model=schemas.QuoteRequestDetailOut,
)
def create_request(
    body: schemas.QuoteRequestIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteRequestDetailOut:
    """Send a structured brief to one provider (PRD §9)."""
    try:
        request = quotes.create_request(
            session, guardian_id=principal.user_id, data=body, email_gateway=email_gateway
        )
    except quotes.OrganisationNotBookable as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "That provider isn't taking enquiries"
        ) from exc
    return _request_detail(session, request)


@router.get("/requests", response_model=list[schemas.QuoteRequestDetailOut])
def my_requests(
    principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.QuoteRequestDetailOut]:
    return [
        _request_detail(session, r)
        for r in quotes.list_guardian_requests(session, principal.user_id)
    ]


@router.get("/requests/{request_id}", response_model=schemas.QuoteRequestDetailOut)
def get_request(
    request_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.QuoteRequestDetailOut:
    request = quotes.get_request(session, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found")
    # Either side of the conversation may read it; nobody else.
    if request.guardian_id != principal.user_id and (
        org_service.get_member(session, request.organisation_id, principal.user_id) is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found")
    return _request_detail(session, request)


@router.post("/requests/{request_id}/withdraw", response_model=schemas.QuoteRequestDetailOut)
def withdraw_request(
    request_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.QuoteRequestDetailOut:
    try:
        request = quotes.withdraw_request(
            session, request_id=request_id, guardian_id=principal.user_id
        )
    except quotes.QuoteRequestNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found") from exc
    except quotes.RequestNotOpen as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This enquiry is already closed") from exc
    return _request_detail(session, request)


@router.post("/{quote_id}/request-revision", response_model=schemas.QuoteDetailOut)
def request_revision(
    quote_id: uuid.UUID,
    body: schemas.RevisionRequestIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteDetailOut:
    """Ask for one revision (ADR-0009). After this it's accept or let it lapse."""
    try:
        quote = quotes.request_revision(
            session, quote_id=quote_id, guardian_id=principal.user_id,
            message=body.message, email_gateway=email_gateway,
        )
    except quotes.QuoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found") from exc
    except quotes.RevisionLimitReached as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You've already asked for a revision — accept the quote or let it lapse",
        ) from exc
    except quotes.QuoteNotOpen as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This quote is no longer open") from exc
    return _quote_detail(session, quote)


@router.post("/{quote_id}/accept", response_model=schemas.PartyBookingOut)
def accept_quote(
    quote_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
    email_gateway: EmailGatewayDep,
) -> schemas.PartyBookingOut:
    """Accept the quote — books its slot and starts the deposit on the existing rails."""
    try:
        _quote, booking, intent = quotes.accept_quote(
            session, quote_id=quote_id, guardian_id=principal.user_id,
            gateway=gateway, email_gateway=email_gateway,
        )
    except quotes.QuoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found") from exc
    except quotes.QuoteNotOpen as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This quote is no longer available to accept"
        ) from exc
    except service.SlotUnavailable as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That date is no longer available"
        ) from exc
    return schemas.PartyBookingOut(
        id=booking.id,
        slot_id=booking.slot_id,
        package_id=booking.package_id,
        headcount=booking.headcount,
        total_cents=booking.total_cents,
        deposit_cents=booking.deposit_cents,
        balance_cents=booking.balance_cents,
        status=booking.status.value,
        client_secret=intent.client_secret,
    )


# --- Provider ----------------------------------------------------------------


@router.get(
    "/orgs/{organisation_id}/requests", response_model=list[schemas.QuoteRequestDetailOut]
)
def org_requests(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.QuoteRequestDetailOut]:
    """The provider's enquiry inbox."""
    try:
        rows = quotes.list_org_requests(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this provider") from exc
    return [_request_detail(session, r) for r in rows]


@router.post(
    "/requests/{request_id}/quote", status_code=status.HTTP_201_CREATED,
    response_model=schemas.QuoteDetailOut,
)
def send_quote(
    request_id: uuid.UUID,
    body: schemas.QuoteIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteDetailOut:
    """Price the brief. The offer becomes a private package + slot the parent can book."""
    try:
        quote = quotes.send_quote(
            session, request_id=request_id, actor_id=principal.user_id, data=body,
            email_gateway=email_gateway,
        )
    except quotes.QuoteRequestNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this provider") from exc
    except service.VenueNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found") from exc
    except quotes.RequestNotOpen as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This enquiry already has a quote or is closed"
        ) from exc
    return _quote_detail(session, quote)


@router.put("/{quote_id}", response_model=schemas.QuoteDetailOut)
def revise_quote(
    quote_id: uuid.UUID,
    body: schemas.QuoteIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteDetailOut:
    """Send the one revised offer, in reply to the parent's ask."""
    try:
        quote = quotes.revise_quote(
            session, quote_id=quote_id, actor_id=principal.user_id, data=body,
            email_gateway=email_gateway,
        )
    except quotes.QuoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this provider") from exc
    except service.VenueNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venue not found") from exc
    except quotes.RevisionNotRequested as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The family hasn't asked for a revision"
        ) from exc
    except quotes.RevisionLimitReached as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "A quote can be revised once") from exc
    return _quote_detail(session, quote)


@router.post("/{quote_id}/withdraw", response_model=schemas.QuoteDetailOut)
def withdraw_quote(
    quote_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteDetailOut:
    try:
        quote = quotes.withdraw_quote(
            session, quote_id=quote_id, actor_id=principal.user_id, email_gateway=email_gateway
        )
    except quotes.QuoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quote not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this provider") from exc
    except quotes.QuoteNotOpen as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This quote is already closed") from exc
    return _quote_detail(session, quote)


@router.post("/requests/{request_id}/decline", response_model=schemas.QuoteRequestDetailOut)
def decline_request(
    request_id: uuid.UUID,
    principal: CurrentPrincipal,
    session: SessionDep,
    email_gateway: EmailGatewayDep,
) -> schemas.QuoteRequestDetailOut:
    """Pass on a brief without quoting."""
    try:
        request = quotes.decline_request(
            session, request_id=request_id, actor_id=principal.user_id,
            email_gateway=email_gateway,
        )
    except quotes.QuoteRequestNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Enquiry not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this provider") from exc
    except quotes.RequestNotOpen as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "This enquiry is already closed") from exc
    return _request_detail(session, request)
