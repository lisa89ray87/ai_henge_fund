"""Database health checks that do not expose connection details."""

from dataclasses import dataclass

from sqlalchemy import Engine, text

from ai_henge_fund.database.engine import get_engine


@dataclass(frozen=True)
class DatabaseHealth:
    """Sanitized result of a database connectivity check."""

    healthy: bool
    message: str


class DatabaseConnectionError(RuntimeError):
    """A sanitized database connectivity error safe to surface to callers."""


def check_database_health(engine: Engine | None = None) -> DatabaseHealth:
    """Execute ``SELECT 1`` and return a sanitized health result."""
    try:
        database_engine = engine or get_engine()
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - sanitize all driver failures before returning them.
        return DatabaseHealth(healthy=False, message="Database health check failed.")

    return DatabaseHealth(healthy=True, message="Database health check succeeded.")


def check_database_connection(engine: Engine | None = None) -> None:
    """Verify connectivity and raise a sanitized error instead of leaking driver details."""
    result = check_database_health(engine)
    if not result.healthy:
        raise DatabaseConnectionError(result.message)
