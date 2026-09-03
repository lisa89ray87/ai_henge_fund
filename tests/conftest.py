import pytest

from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.database import engine, session


@pytest.fixture(autouse=True)
def isolate_test_environment(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests run under an isolated SQLite test database and test app environment."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./ai_henge_fund_test.db")
    monkeypatch.setenv("MOOMOO_LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("AI_HEDGE_FUND_LIVE_TRADING_ARMED", "false")
    monkeypatch.setenv("MOOMOO_READ_ONLY", "true")
    monkeypatch.setenv("MOOMOO_PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("EXECUTE_PAPER", "true")

    get_settings.cache_clear()
    engine.get_engine.cache_clear()
    session.get_session_factory.cache_clear()

    yield

    get_settings.cache_clear()
    engine.get_engine.cache_clear()
    session.get_session_factory.cache_clear()
