"""Business logic for the identity module.

All mutations funnel through a module service (no side-door SQL) so the admin
panel and product share one code path (PRD §10.4).
"""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from juggle.modules.identity.core.models import Child, UserAccount, UserStatus
from juggle.modules.identity.core.schemas import ChildCreate
from juggle.security import hash_password, verify_password


class EmailAlreadyExists(Exception):
    """Raised when signing up with an email that is already registered."""


def create_guardian(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str | None = None,
    phone: str | None = None,
) -> UserAccount:
    if session.scalar(select(UserAccount).where(UserAccount.email == email)) is not None:
        raise EmailAlreadyExists(email)
    user = UserAccount(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, *, email: str, password: str) -> UserAccount | None:
    user = session.scalar(select(UserAccount).where(UserAccount.email == email))
    if user is None or user.password_hash is None:
        return None
    if user.status is not UserStatus.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user(session: Session, user_id: uuid.UUID) -> UserAccount | None:
    return session.get(UserAccount, user_id)


def search_users(session: Session, *, query: str, limit: int = 20) -> list[UserAccount]:
    """Find users by email or name fragment — an admin support lookup (PRD §10.2)."""
    like = f"%{query}%"
    return list(
        session.scalars(
            select(UserAccount)
            .where(or_(UserAccount.email.ilike(like), UserAccount.full_name.ilike(like)))
            .order_by(UserAccount.email)
            .limit(max(1, min(limit, 50)))
        )
    )


def add_child(session: Session, *, guardian_id: uuid.UUID, data: ChildCreate) -> Child:
    child = Child(guardian_id=guardian_id, **data.model_dump())
    session.add(child)
    session.flush()
    return child


def list_children(session: Session, guardian_id: uuid.UUID) -> list[Child]:
    return list(
        session.scalars(
            select(Child).where(Child.guardian_id == guardian_id).order_by(Child.created_at)
        )
    )
