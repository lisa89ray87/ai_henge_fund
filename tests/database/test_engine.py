"""Tests for lazy SQLAlchemy engine and session construction."""

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from ai_henge_fund.config.settings import AppSettings
from ai_henge_fund.database import engine, session


@pytest.fixture(autouse=True)
def clear_database_caches() -> None:
    """Ensure each test observes lazy engine and session construction."""
    engine.get_engine.cache_clear()
    session.get_session_factory.cache_clear()
    yield
    engine.get_engine.cache_clear()
    session.get_session_factory.cache_clear()


def test_engine_is_not_created_during_module_import() -> None:
    assert engine.get_engine.cache_info().currsize == 0


def test_test_configuration_does_not_require_a_database_url() -> None:
    settings = AppSettings(_env_file=None, app_env="test", debug=False, database_url=None)

    assert settings.database_url is None


def test_engine_uses_psycopg_url_and_production_pool_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://user:password@example.neon.tech/database?sslmode=require"
    monkeypatch.setattr(
        engine,
        "get_settings",
        lambda: SimpleNamespace(database_url=SecretStr(database_url)),
    )

    database_engine = engine.get_engine()

    assert database_engine.url.drivername == "postgresql+psycopg"
    assert database_engine.pool._pre_ping is True
    assert database_engine.pool.size() == 5
    assert database_engine.pool._max_overflow == 10
    assert database_engine.pool._recycle == 1800


def test_session_factory_can_be_constructed_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://user:password@example.neon.tech/database?sslmode=require"
    database_engine = engine.create_database_engine(database_url)
    monkeypatch.setattr(session, "get_engine", lambda: database_engine)

    factory = session.get_session_factory()

    assert factory.kw["bind"] is database_engine
