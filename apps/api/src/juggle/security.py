"""Password hashing and JWT primitives — pure, framework-free.

Lives outside the module packages (like ``common``) so any module's ``core``
may issue/verify tokens without importing another module or FastAPI. The
FastAPI auth dependency that consumes these lives in ``juggle.deps``.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from juggle.settings import get_settings

# bcrypt hashes at most 72 bytes; longer inputs are truncated (standard practice).
_BCRYPT_MAX_BYTES = 72


def hash_password(raw: str) -> str:
    digest = bcrypt.hashpw(raw.encode("utf-8")[:_BCRYPT_MAX_BYTES], bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8")[:_BCRYPT_MAX_BYTES], hashed.encode("utf-8"))


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, decoded from a JWT. No DB lookup involved.

    During impersonation the JWT carries the target user in ``sub`` and the real
    admin in ``impersonator_id`` (PRD §10.3) — the true actor is never lost.
    """

    user_id: uuid.UUID
    is_admin: bool
    impersonator_id: uuid.UUID | None = None
    impersonation_mode: str | None = None  # "view_as" | "act_as"
    impersonation_session_id: uuid.UUID | None = None

    @property
    def is_impersonating(self) -> bool:
        return self.impersonator_id is not None


def create_access_token(user_id: uuid.UUID, is_admin: bool = False) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "adm": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_impersonation_token(
    *,
    target_id: uuid.UUID,
    impersonator_id: uuid.UUID,
    mode: str,
    session_id: uuid.UUID,
    ttl_minutes: int,
) -> str:
    """A scoped, time-boxed token to act as ``target_id``. ``adm`` is forced
    False so impersonation can never escalate to admin capabilities."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(target_id),
        "adm": False,
        "imp": str(impersonator_id),
        "mode": mode,
        "isid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Principal:
    """Decode/verify a token. Raises ``jwt.PyJWTError`` on any problem."""
    settings = get_settings()
    data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    impersonator = data.get("imp")
    session_id = data.get("isid")
    return Principal(
        user_id=uuid.UUID(data["sub"]),
        is_admin=bool(data.get("adm", False)),
        impersonator_id=uuid.UUID(impersonator) if impersonator else None,
        impersonation_mode=data.get("mode"),
        impersonation_session_id=uuid.UUID(session_id) if session_id else None,
    )
