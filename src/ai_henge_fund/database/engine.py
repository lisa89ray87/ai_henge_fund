"""Lazy SQLAlchemy engine construction for Neon PostgreSQL."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from ai_henge_fund.config.settings import get_settings


def normalize_database_url(database_url: str) -> str:
    """Normalize PostgreSQL URLs to the project's psycopg 3 driver."""
    value = database_url.strip()
    if not value:
        raise ValueError("DATABASE_URL must not be empty.")

    parsed = make_url(value)
    if parsed.drivername in {"postgres", "postgresql", "postgresql+psycopg2"}:
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed.render_as_string(hide_password=False)


def create_database_engine(database_url: str) -> Engine:
    """Create a pooled SQLAlchemy 2.x engine without opening a connection."""
    return create_engine(
        normalize_database_url(database_url),
        future=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
    )


@lru_cache
def get_engine() -> Engine:
    """Return the cached database engine, creating it only on first use."""
    database_url = get_settings().database_url
    if database_url is None or not database_url.get_secret_value().strip():
        raise RuntimeError("DATABASE_URL must be configured before creating a database engine.")

    return create_database_engine(database_url.get_secret_value())
