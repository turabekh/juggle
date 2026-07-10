"""HTTP routes for the identity module: auth + guardian family profiles."""

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
