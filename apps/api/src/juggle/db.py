"""Database engine, session factory, and declarative Base.

Inventory correctness is the product (PRD §12): seat holds use row locks and
oversell is forbidden by DB constraint. Keep transaction boundaries explicit in
module services; this file only wires up the engine and session lifecycle.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from juggle.settings import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    echo=_settings.debug,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models across every module."""


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
