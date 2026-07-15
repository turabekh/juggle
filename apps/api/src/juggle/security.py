"""Password hashing and JWT primitives — pure, framework-free.

Lives outside the module packages (like ``common``) so any module's ``core``
may issue/verify tokens without importing another module or FastAPI. The
FastAPI auth dependency that consumes these lives in ``juggle.deps``.
"""

import hashlib
import hmac
import secrets
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


# --- opaque secrets (refresh tokens, OTP codes) ------------------------------
#
# Refresh tokens are high-entropy random strings, so a fast SHA-256 (not bcrypt)
# is the right digest: we only ever store the hash, and lookups compare hashes.
# OTP codes are low-entropy, so their digest is salted with the JWT secret to
# frustrate offline guessing of a leaked table (they are also short-lived).


def generate_refresh_token() -> str:
    """A URL-safe, high-entropy opaque token handed to the client (never stored raw)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_otp_code() -> str:
    """A 6-digit numeric code (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    """Keyed digest so a leaked challenge table can't be brute-forced offline."""
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_secret(raw: str, hashed: str) -> bool:
    """Constant-time compare of a raw refresh token against its stored SHA-256."""
    return hmac.compare_digest(hash_refresh_token(raw), hashed)


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
