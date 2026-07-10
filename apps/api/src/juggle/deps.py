"""Shared FastAPI dependencies (auth). Only the ``ui`` layer imports this."""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from juggle.security import Principal, decode_token

_bearer = HTTPBearer(auto_error=True)


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> Principal:
    """Resolve the caller from a ``Bearer`` token, or 401."""
    try:
        return decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_admin(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
CurrentAdmin = Annotated[Principal, Depends(get_current_admin)]
