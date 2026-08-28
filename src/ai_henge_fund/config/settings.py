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

    # Moomoo market data / OpenD
    moomoo_mcp_enabled: bool = False
    moomoo_mcp_url: str | None = None
    moomoo_read_only: bool = True
    s_only: bool = True
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = 11111

    # Moomoo paper execution. This is the only execution mode currently allowed.
    moomoo_paper_trading_enabled: bool = False
    moomoo_live_trading_enabled: bool = False
    moomoo_paper_fill_timeout_seconds: int = 30

    # AI Henge Fund capital / risk budget. These limits apply to the dedicated
    # strategy allocation, not to the user's entire Moomoo account balance.
    ai_henge_fund_starting_capital: float = 100.0
    ai_henge_fund_max_capital_deployed: float = 90.0
    ai_henge_fund_risk_per_trade_pct: float = 50.0
    ai_henge_fund_max_positions: int = 0  # 0 = no fixed count limit
    ai_henge_fund_max_daily_loss: float = 10.0

    # Streamlit
    streamlit_server_port: int = 8501

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_stage_safety(self) -> "AppSettings":
        """Require a DB outside tests and permanently fail closed for live trading."""
        if self.app_env != "test" and (
            self.database_url is None or not self.database_url.get_secret_value().strip()
        ):
            raise ValueError("DATABASE_URL must be provided when APP_ENV is not 'test'.")

        if not self.moomoo_read_only:
            raise ValueError(
                "Moomoo must remain read-only. "
                "Live Moomoo market-data access cannot be used for trading."
            )

        if self.moomoo_live_trading_enabled:
            raise ValueError(
                "Live Moomoo trading is disabled by project safety policy. "
                "Only the SIMULATE paper environment is supported."
            )

        if self.moomoo_paper_fill_timeout_seconds < 1:
            raise ValueError("MOOMOO_PAPER_FILL_TIMEOUT_SECONDS must be at least 1 second.")

        if self.ai_henge_fund_starting_capital <= 0:
            raise ValueError("AI_HEDGE_FUND_STARTING_CAPITAL must be greater than zero.")
        if self.ai_henge_fund_max_capital_deployed <= 0:
            raise ValueError("AI_HEDGE_FUND_MAX_CAPITAL_DEPLOYED must be greater than zero.")
        if self.ai_henge_fund_max_capital_deployed > self.ai_henge_fund_starting_capital:
            raise ValueError("AI_HEDGE_FUND_MAX_CAPITAL_DEPLOYED cannot exceed starting capital.")
        if not 0 <= self.ai_henge_fund_risk_per_trade_pct <= 100:
            raise ValueError("AI_HEDGE_FUND_RISK_PER_TRADE_PCT must be between 0 and 100.")
        if self.ai_henge_fund_max_positions < 0:
            raise ValueError("AI_HEDGE_FUND_MAX_POSITIONS must be zero or greater.")
        if self.ai_henge_fund_max_daily_loss <= 0:
            raise ValueError("AI_HEDGE_FUND_MAX_DAILY_LOSS must be greater than zero.")

        return self


@lru_cache
def get_settings() -> AppSettings:
    """Return the process-wide cached application settings instance."""
    return AppSettings()
