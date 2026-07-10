"""Alembic environment — pulls the DB URL from app settings and Base metadata.

``juggle.models`` is imported so ``Base.metadata`` is fully populated for
autogenerate. Reflection is pinned to the ``public`` schema so the PostGIS
image's tiger/topology extension tables (which sit on the DB search_path) don't
get swept into migrations.
"""

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine, pool

import juggle.models  # noqa: F401  — registers every module's models on Base.metadata
from juggle.db import Base
from juggle.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=alembic_helpers.render_item,
        include_object=alembic_helpers.include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Pin search_path to public at connect time (via libpq options) so the
    # PostGIS image's tiger/topology schemas don't leak into reflection/DDL.
    # Doing it here — rather than a mid-transaction SET — avoids opening a
    # transaction before Alembic manages one (which would roll the run back).
    connectable = create_engine(
        get_settings().database_url,
        poolclass=pool.NullPool,
        connect_args={"options": "-csearch_path=public"},
    )
    with connectable.connect() as connection:
        # GeoAlchemy2 alembic helpers: render spatial types, create spatial
        # indexes, and skip PostGIS-managed system tables during autogenerate.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
            include_object=alembic_helpers.include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
