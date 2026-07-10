"""Pytest fixtures. DB-backed tests use a live Postgres and roll back per test.

They skip cleanly when Postgres is unreachable or unmigrated, so ``make test``
still runs the pure-unit tests without Docker.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from juggle.settings import get_settings


@pytest.fixture(scope="session")
def engine() -> Engine:
    eng = create_engine(
        get_settings().database_url,
        connect_args={"options": "-csearch_path=public"},
    )
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no DB"
        pytest.skip(f"Postgres not reachable ({exc}); run `make db`.")
    if not inspect(eng).has_table("session"):
        pytest.skip("Schema not migrated; run `make migrate`.")
    return eng


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session wrapped in a transaction that is rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        # A failed flush already aborts the transaction; only roll back if it
        # is still active to avoid a spurious "already deassociated" warning.
        if transaction.is_active:
            transaction.rollback()
        connection.close()
