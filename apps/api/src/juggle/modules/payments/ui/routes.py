"""HTTP routes for the payments module: Connect onboarding, status, payouts, and
reading a payment's status. The Stripe webhook sink lives in the booking module
(it must orchestrate settlement, which is above payments in the layering)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.payments.core import schemas, service
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway
from juggle.settings import get_settings

router = APIRouter(prefix="/payments", tags=["payments"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]


@router.post("/connect/onboard", response_model=schemas.OnboardLinkOut)
def start_onboarding(
    body: schemas.OnboardIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.OnboardLinkOut:
    """Create/reuse the org's Stripe Express account and return a hosted onboarding link."""
    base = get_settings().public_base_url
    try:
        link = service.start_onboarding(
            session,
            organisation_id=body.organisation_id,
            actor_id=principal.user_id,
            gateway=gateway,
            refresh_url=body.refresh_url or f"{base}/provider/orgs/{body.organisation_id}",
            return_url=body.return_url or f"{base}/provider/orgs/{body.organisation_id}",
        )
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return schemas.OnboardLinkOut(url=link.url)


@router.get("/connect/status", response_model=schemas.ConnectStatusOut)
def connect_status(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.ConnectStatusOut:
    try:
        state = service.connect_status(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return schemas.ConnectStatusOut(**state)


@router.post("/connect/refresh", response_model=schemas.ConnectStatusOut)
def refresh_status(
    body: schemas.RefreshIn,
    principal: CurrentPrincipal,
    session: SessionDep,
    gateway: GatewayDep,
) -> schemas.ConnectStatusOut:
    """Re-pull capability flags from Stripe (called on onboarding return)."""
    try:
        service.connect_status(
            session, organisation_id=body.organisation_id, actor_id=principal.user_id
        )
        state = service.refresh_account_status(
            session, organisation_id=body.organisation_id, gateway=gateway
        )
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return schemas.ConnectStatusOut(**state)


@router.get("/payouts", response_model=list[schemas.PayoutOut])
def list_payouts(
    organisation_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.PayoutOut]:
    """A provider's payouts for one org (member-gated)."""
    try:
        payouts = service.list_org_payouts(
            session, organisation_id=organisation_id, actor_id=principal.user_id
        )
    except service.NotOrgMember as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Not a member of this organisation"
        ) from exc
    return [schemas.PayoutOut.model_validate(p) for p in payouts]


@router.get("/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(
    payment_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.PaymentOut:
    payment = service.get_payment(session, payment_id)
    if payment is None or payment.guardian_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    return schemas.PaymentOut.model_validate(payment)
