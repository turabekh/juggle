"""HTTP routes for the identity module: auth + guardian family profiles."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.identity.core import schemas, service
from juggle.modules.identity.core.models import UserAccount
from juggle.modules.notifications.core.gateway import (
    SmsGateway,
    get_sms_gateway,
    sms_available,
)
from juggle.security import create_access_token
from juggle.settings import get_settings

router = APIRouter(prefix="/identity", tags=["identity"])

SessionDep = Annotated[Session, Depends(get_session)]
SmsGatewayDep = Annotated[SmsGateway, Depends(get_sms_gateway)]


def _tokens(session: Session, user: UserAccount) -> schemas.TokenResponse:
    """Build an access + refresh pair for a freshly authenticated user."""
    settings = get_settings()
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, user.is_admin),
        refresh_token=service.issue_refresh_token(session, user_id=user.id),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=schemas.TokenResponse)
def signup(payload: schemas.SignupRequest, session: SessionDep) -> schemas.TokenResponse:
    try:
        user = service.create_guardian(
            session,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            phone=payload.phone,
        )
    except service.EmailAlreadyExists as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc
    return _tokens(session, user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, session: SessionDep) -> schemas.TokenResponse:
    user = service.authenticate(session, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _tokens(session, user)


_EXPIRED_SESSION = "Session expired, please sign in again"


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(
    payload: schemas.RefreshRequest, session: SessionDep
) -> schemas.TokenResponse | JSONResponse:
    """Rotate a refresh token into a new access+refresh pair (see service)."""
    try:
        user, new_refresh = service.rotate_refresh_token(session, raw=payload.refresh_token)
    except service.RefreshTokenReuse:
        # Reuse revoked the whole family; return (don't raise) so that write commits.
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": _EXPIRED_SESSION},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except service.InvalidRefreshToken as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _EXPIRED_SESSION,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    settings = get_settings()
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, user.is_admin),
        refresh_token=new_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.LogoutRequest, session: SessionDep) -> None:
    """Revoke the presented refresh token so the session is truly dead."""
    service.revoke_refresh_token(session, raw=payload.refresh_token)


@router.get("/auth-config", response_model=schemas.AuthConfig)
def auth_config() -> schemas.AuthConfig:
    """Public: what sign-in methods are available (drives the login UI)."""
    return schemas.AuthConfig(sms_enabled=sms_available())


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
def otp_request(
    payload: schemas.OtpRequest, session: SessionDep, gateway: SmsGatewayDep
) -> dict[str, str]:
    """Text a one-time sign-in code. Always 202 (never reveals whether the number
    is registered); rate-limited per number. Fail-closed if SMS isn't configured."""
    if not sms_available():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "SMS sign-in is not available"
        )
    try:
        service.request_otp(session, phone=payload.phone, gateway=gateway)
    except service.OtpRateLimited as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Please wait {exc} seconds before requesting another code",
        ) from exc
    return {"status": "sent"}


@router.post("/otp/verify", response_model=schemas.TokenResponse)
def otp_verify(payload: schemas.OtpVerify, session: SessionDep) -> schemas.TokenResponse:
    """Verify a code and sign in (creating a phone-first account if new)."""
    if not sms_available():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "SMS sign-in is not available"
        )
    try:
        user = service.verify_otp(session, phone=payload.phone, code=payload.code)
    except service.InvalidOtp as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired code") from exc
    return _tokens(session, user)


@router.get("/me", response_model=schemas.UserOut)
def me(principal: CurrentPrincipal, session: SessionDep) -> schemas.UserOut:
    user = service.get_user(session, principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return schemas.UserOut.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(principal: CurrentPrincipal, session: SessionDep) -> None:
    """Self-service account + data deletion (APP compliance, PRD §10.2)."""
    service.delete_account(session, user_id=principal.user_id, actor_id=principal.user_id)


@router.post(
    "/children", status_code=status.HTTP_201_CREATED, response_model=schemas.ChildOut
)
def add_child(
    payload: schemas.ChildCreate, principal: CurrentPrincipal, session: SessionDep
) -> schemas.ChildOut:
    child = service.add_child(session, guardian_id=principal.user_id, data=payload)
    return schemas.ChildOut.model_validate(child)


@router.get("/children", response_model=list[schemas.ChildOut])
def list_children(principal: CurrentPrincipal, session: SessionDep) -> list[schemas.ChildOut]:
    children = service.list_children(session, principal.user_id)
    return [schemas.ChildOut.model_validate(c) for c in children]


# --- co-guardians (PRD §7.3) -------------------------------------------------


@router.get("/co-guardians", response_model=list[schemas.CoGuardianOut])
def list_co_guardians(
    principal: CurrentPrincipal, session: SessionDep
) -> list[schemas.CoGuardianOut]:
    return service.list_co_guardians(session, principal.user_id)


@router.post(
    "/co-guardians", status_code=status.HTTP_201_CREATED, response_model=schemas.CoGuardianOut
)
def invite_co_guardian(
    payload: schemas.CoGuardianInvite, principal: CurrentPrincipal, session: SessionDep
) -> schemas.CoGuardianOut:
    try:
        service.invite_co_guardian(session, owner_id=principal.user_id, email=payload.email)
    except service.CoGuardianNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No Juggle account with that email"
        ) from exc
    except service.CannotLinkSelf as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "That's you!") from exc
    except service.AlreadyLinked as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You're already linked with this person"
        ) from exc
    # Return the fresh view from the inviter's side.
    return next(
        c for c in service.list_co_guardians(session, principal.user_id)
        if c.other_email == payload.email
    )


@router.post("/co-guardians/{link_id}/accept", response_model=schemas.CoGuardianOut)
def accept_co_guardian(
    link_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> schemas.CoGuardianOut:
    try:
        service.accept_co_guardian(session, user_id=principal.user_id, link_id=link_id)
    except service.LinkNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found") from exc
    return next(
        c for c in service.list_co_guardians(session, principal.user_id) if c.id == link_id
    )


@router.delete("/co-guardians/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_co_guardian(
    link_id: uuid.UUID, principal: CurrentPrincipal, session: SessionDep
) -> None:
    try:
        service.remove_co_guardian(session, user_id=principal.user_id, link_id=link_id)
    except service.LinkNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found") from exc
