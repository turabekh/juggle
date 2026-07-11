"""HTTP routes for the identity module: auth + guardian family profiles."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.deps import CurrentPrincipal
from juggle.modules.identity.core import schemas, service
from juggle.security import create_access_token

router = APIRouter(prefix="/identity", tags=["identity"])

SessionDep = Annotated[Session, Depends(get_session)]


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
    return schemas.TokenResponse(access_token=create_access_token(user.id, user.is_admin))


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, session: SessionDep) -> schemas.TokenResponse:
    user = service.authenticate(session, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return schemas.TokenResponse(access_token=create_access_token(user.id, user.is_admin))


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
