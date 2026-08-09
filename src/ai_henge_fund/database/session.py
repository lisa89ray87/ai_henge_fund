"""SQLAlchemy session factory and transaction helper."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from ai_henge_fund.database.engine import get_engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the cached SQLAlchemy session factory without connecting to PostgreSQL."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Yield a transaction-bound session that commits or rolls back safely."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
