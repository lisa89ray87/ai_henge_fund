"""Lazy SQLAlchemy engine construction for Neon PostgreSQL."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from ai_henge_fund.config.settings import get_settings


def create_database_engine(database_url: str) -> Engine:
    """Create a pooled SQLAlchemy 2.x engine without opening a connection."""
    return create_engine(
        database_url,
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
