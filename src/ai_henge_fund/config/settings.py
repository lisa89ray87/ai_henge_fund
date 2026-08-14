"""Typed, environment-based application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Configuration loaded from environment variables and an optional ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "AI Henge Fund"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # LLM providers
    # OpenAI remains the primary provider when both keys are available.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1"
    gemini_api_key: SecretStr | None = None
    gemini_deep_think_llm: str = "gemini-2.5-pro"
    gemini_quick_think_llm: str = "gemini-2.5-flash"

    # Database
    database_url: SecretStr | None = None

    # TradingAgents
    tradingagents_llm_provider: str = "openai"
    tradingagents_deep_think_llm: str = "gpt-4.1"
    tradingagents_quick_think_llm: str = "gpt-4.1-mini"
    tradingagents_backend_url: str | None = None

    # Moomoo MCP: this integration is intentionally read-only in Stages 1 and 2.
    moomoo_mcp_enabled: bool = False
    moomoo_mcp_url: str | None = None
    moomoo_read_only: bool = True
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = 11111

    # Streamlit
    streamlit_server_port: int = 8501

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        """Normalize log levels so downstream logging receives a consistent value."""
        return value.upper()

    @model_validator(mode="after")
    def validate_stage_safety(self) -> "AppSettings":
        """Enforce Stage 1/2 database and Moomoo safety constraints."""
        if self.app_env != "test" and (
            self.database_url is None or not self.database_url.get_secret_value().strip()
        ):
            raise ValueError("DATABASE_URL must be provided when APP_ENV is not 'test'.")

        if not self.moomoo_read_only:
            raise ValueError("Moomoo must remain read-only during Stage 1 and Stage 2.")

        return self


@lru_cache
def get_settings() -> AppSettings:
    """Return the process-wide cached application settings instance."""
    return AppSettings()
