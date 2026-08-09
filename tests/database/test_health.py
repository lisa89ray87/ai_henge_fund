"""Tests for sanitized database health checks."""

from unittest.mock import MagicMock

import pytest

from ai_henge_fund.database.health import (
    DatabaseConnectionError,
    check_database_connection,
    check_database_health,
)


def test_health_check_returns_success_for_select_one() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection
    database_engine = MagicMock()
    database_engine.connect.return_value = connection

    result = check_database_health(database_engine)

    assert result.healthy is True
    assert result.message == "Database health check succeeded."
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"


def test_health_check_sanitizes_connection_failures() -> None:
    database_engine = MagicMock()
    database_engine.connect.side_effect = RuntimeError(
        "connection failed for postgresql://user:password@example.neon.tech/database"
    )

    result = check_database_health(database_engine)

    assert result.healthy is False
    assert result.message == "Database health check failed."
    assert "password" not in result.message
    assert "postgresql" not in result.message


def test_connection_check_raises_a_sanitized_error() -> None:
    database_engine = MagicMock()
    database_engine.connect.side_effect = RuntimeError(
        "connection failed for postgresql://user:password@example.neon.tech/database"
    )

    with pytest.raises(DatabaseConnectionError, match="Database health check failed") as error:
        check_database_connection(database_engine)

    assert "password" not in str(error.value)
