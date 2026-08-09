"""Tests for typed application configuration."""

import pytest
from pydantic import SecretStr, ValidationError

from ai_henge_fund.config.settings import AppSettings


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent machine-level environment variables from affecting settings tests."""
    for variable in (
        "APP_NAME",
        "APP_ENV",
        "DEBUG",
        "LOG_LEVEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "DATABASE_URL",
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_DEEP_THINK_LLM",
        "TRADINGAGENTS_QUICK_THINK_LLM",
        "TRADINGAGENTS_BACKEND_URL",
        "MOOMOO_MCP_ENABLED",
        "MOOMOO_MCP_URL",
        "MOOMOO_READ_ONLY",
        "MOOMOO_OPEND_HOST",
        "MOOMOO_OPEND_PORT",
        "STREAMLIT_SERVER_PORT",
    ):
        monkeypatch.delenv(variable, raising=False)


def test_defaults_load_correctly() -> None:
    settings = AppSettings(_env_file=None, app_env="test")

    assert settings.app_name == "AI Henge Fund"
    assert settings.app_env == "test"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.streamlit_server_port == 8501


def test_moomoo_defaults_to_disabled() -> None:
    settings = AppSettings(_env_file=None, app_env="test")

    assert settings.moomoo_mcp_enabled is False


def test_moomoo_defaults_to_read_only() -> None:
    settings = AppSettings(_env_file=None, app_env="test")

    assert settings.moomoo_read_only is True


def test_secrets_are_represented_correctly() -> None:
    settings = AppSettings(
        _env_file=None,
        app_env="test",
        openai_api_key="test-openai-key",
        database_url="postgresql+psycopg2://user:password@host/database",
    )

    assert isinstance(settings.openai_api_key, SecretStr)
    assert isinstance(settings.database_url, SecretStr)
    assert "test-openai-key" not in repr(settings)
    assert "password" not in repr(settings)


def test_non_test_environment_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must be provided"):
        AppSettings(_env_file=None, app_env="development")


def test_invalid_debug_value_is_rejected_directly() -> None:
    with pytest.raises(ValidationError, match="boolean|Unable to parse"):
        AppSettings(_env_file=None, app_env="test", debug="release")


def test_invalid_debug_environment_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "release")
    with pytest.raises(ValidationError, match="boolean|Unable to parse"):
        AppSettings(_env_file=None, app_env="test")


def test_moomoo_read_only_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError, match="Moomoo must remain read-only"):
        AppSettings(_env_file=None, app_env="test", moomoo_read_only=False)
