"""Alembic environment configured from the application settings."""

from logging.config import fileConfig

from alembic import context
from alembic.config import Config
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.database.base import Base


def load_model_metadata() -> None:
    """Import all mapped models before Alembic reads the shared metadata."""
    from ai_henge_fund.database import models

    _ = models


load_model_metadata()


target_metadata = Base.metadata


def get_alembic_config() -> Config:
    """Return Alembic's active configuration only while a command is executing."""
    return context.config


def configure_logging() -> None:
    """Configure Alembic logging without adding the database URL to configuration."""
    config = get_alembic_config()
    if config.config_file_name is not None:
        fileConfig(config.config_file_name, disable_existing_loggers=False)


def get_database_url() -> str:
    """Return the configured database URL without logging or persisting it."""
    database_url = get_settings().database_url
    if database_url is None or not database_url.get_secret_value().strip():
        raise RuntimeError("DATABASE_URL must be configured before running migrations.")

    value = database_url.get_secret_value().strip()
    parsed = make_url(value)

    # The project standard is psycopg 3. Normalize generic PostgreSQL URLs so
    # Alembic never falls back to SQLAlchemy's legacy psycopg2 dialect.
    if parsed.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        parsed = parsed.set(drivername="postgresql+psycopg")

    return parsed.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using the same configured URL as the application."""
    connectable = create_engine(
        get_database_url(),
        pool_pre_ping=True,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


def run_migrations() -> None:
    """Dispatch to the appropriate migration mode when Alembic executes this file."""
    configure_logging()
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()


# Alembic loads environment scripts under this module name. Normal imports remain inert.
if __name__ == "env_py":
    run_migrations()
