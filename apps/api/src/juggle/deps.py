"""Shared FastAPI dependencies (auth + impersonation guard). ui-layer only."""

from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from juggle.db import get_session
from juggle.modules.audit.core import service as audit_service
from juggle.security import Principal, decode_token

_bearer = HTTPBearer(auto_error=True)
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Principal:
    """Resolve the caller from a ``Bearer`` token, or 401.

    When the token is an impersonation token, enforce PRD §10.3: ``view_as`` is
    read-only, and every mutating action is written to the audit trail with the
    true actor (the impersonator) recorded alongside the target.
    """
    try:
        principal = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if principal.is_impersonating:
        # An ended or expired session invalidates the token immediately (PRD §10.3).
        active = (
            principal.impersonation_session_id is not None
            and _impersonation_active(session, principal.impersonation_session_id)
        )
        if not active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Impersonation session has ended",
            )
        if request.method not in _SAFE_METHODS:
            if principal.impersonation_mode == "view_as":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This is a read-only (view-as) support session",
                )
            # act_as: allow, but record the action with the true actor.
            audit_service.record(
                session,
                action=f"impersonation.{request.method.lower()}",
                actor_id=principal.impersonator_id,
                impersonated_id=principal.user_id,
                entity_type="http",
                entity_id=request.url.path,
                detail={"mode": principal.impersonation_mode},
            )

    return principal


def _impersonation_active(session: Session, session_id: object) -> bool:
    # Queried by table name (not the admin model) so this auth infra stays
    # decoupled from the admin module — deps is imported by every module's ui.
    row = session.execute(
        text("SELECT ended_at, expires_at FROM impersonation_session WHERE id = :id"),
        {"id": str(session_id)},
    ).first()
    if row is None:
        return False
    ended_at, expires_at = row
    return ended_at is None and expires_at > datetime.now(UTC)


def get_current_admin(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
CurrentAdmin = Annotated[Principal, Depends(get_current_admin)]
