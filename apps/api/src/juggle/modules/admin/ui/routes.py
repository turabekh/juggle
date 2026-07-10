"""HTTP routes for the admin module: provider approval, bookings console, and
impersonation (all admin-only)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentAdmin
from juggle.modules.admin.core import schemas, service
from juggle.modules.booking.core.schemas import OrderOut
from juggle.modules.org.core.models import OrgStatus
from juggle.modules.payments.core.gateway import PaymentGateway, get_payment_gateway

router = APIRouter(prefix="/admin", tags=["admin"])

SessionDep = Annotated[Session, Depends(get_session)]
GatewayDep = Annotated[PaymentGateway, Depends(get_payment_gateway)]


# --- Provider approval ------------------------------------------------------

@router.get("/orgs", response_model=list[schemas.OrgAdminOut])
def list_orgs(
    admin: CurrentAdmin,
    session: SessionDep,
    status_filter: Annotated[
        Literal["pending", "approved", "suspended"], Query(alias="status")
    ] = "pending",
) -> list[schemas.OrgAdminOut]:
    orgs = service.list_orgs(session, OrgStatus(status_filter))
    return [schemas.OrgAdminOut.model_validate(o) for o in orgs]


@router.post("/orgs/{org_id}/approve", response_model=schemas.OrgAdminOut)
def approve_org(
    org_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> schemas.OrgAdminOut:
    try:
        org = service.approve_org(session, org_id=org_id, actor_id=admin.user_id)
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    return schemas.OrgAdminOut.model_validate(org)


@router.post("/orgs/{org_id}/suspend", response_model=schemas.OrgAdminOut)
def suspend_org(
    org_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> schemas.OrgAdminOut:
    try:
        org = service.suspend_org(session, org_id=org_id, actor_id=admin.user_id)
    except service.OrgNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation not found") from exc
    return schemas.OrgAdminOut.model_validate(org)


# --- Bookings console -------------------------------------------------------

@router.post("/payments/{payment_id}/refund", response_model=OrderOut)
def refund_payment(
    payment_id: uuid.UUID,
    payload: schemas.RefundRequest,
    admin: CurrentAdmin,
    session: SessionDep,
    gateway: GatewayDep,
) -> OrderOut:
    try:
        return service.refund_payment(
            session,
            payment_id=payment_id,
            actor_id=admin.user_id,
            reason=payload.reason,
            gateway=gateway,
        )
    except service.PaymentNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found") from exc


# --- Impersonation ----------------------------------------------------------

@router.post(
    "/impersonations",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ImpersonationTokenOut,
)
def start_impersonation(
    payload: schemas.ImpersonationCreate, admin: CurrentAdmin, session: SessionDep
) -> schemas.ImpersonationTokenOut:
    try:
        session_row, token = service.start_impersonation(
            session,
            impersonator_id=admin.user_id,
            target_user_id=payload.target_user_id,
            mode=payload.mode,
            reason=payload.reason,
        )
    except service.TargetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target user not found") from exc
    except service.CannotImpersonate as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Cannot impersonate this user"
        ) from exc
    return schemas.ImpersonationTokenOut(
        session_id=session_row.id,
        token=token,
        mode=session_row.mode.value,
        expires_at=session_row.expires_at,
    )


@router.get("/impersonations", response_model=list[schemas.ImpersonationSessionOut])
def list_active_impersonations(
    admin: CurrentAdmin, session: SessionDep
) -> list[schemas.ImpersonationSessionOut]:
    rows = service.list_active_impersonations(session)
    return [schemas.ImpersonationSessionOut.model_validate(r) for r in rows]


@router.post("/impersonations/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_impersonation(
    session_id: uuid.UUID, admin: CurrentAdmin, session: SessionDep
) -> None:
    try:
        service.end_impersonation(session, session_id=session_id, actor_id=admin.user_id)
    except service.ImpersonationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Impersonation session not found") from exc
