from __future__ import annotations

import os

from ai_hedge_fund.alerts.telegram import TelegramConfig


AI_HEDGE_FUND_TELEGRAM_BOT_TOKEN = "AI_HEDGE_FUND_TELEGRAM_BOT_TOKEN"
AI_HEDGE_FUND_TELEGRAM_CHAT_ID = "AI_HEDGE_FUND_TELEGRAM_CHAT_ID"


def telegram_config_from_env() -> TelegramConfig:
    """Build the AI Henge Fund Telegram config from its own environment variables."""
    return TelegramConfig(
        bot_token=os.getenv(AI_HEDGE_FUND_TELEGRAM_BOT_TOKEN, "").strip(),
        chat_id=os.getenv(AI_HEDGE_FUND_TELEGRAM_CHAT_ID, "").strip(),
    )
