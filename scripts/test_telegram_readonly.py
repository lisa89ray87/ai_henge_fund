from __future__ import annotations

import os
import sys

from ai_hedge_fund.config.telegram import telegram_config_from_env
from ai_hedge_fund.alerts.telegram import TelegramNotifier


def main() -> int:
    config = telegram_config_from_env()
    if not config.enabled:
        print("TELEGRAM TEST: SKIPPED")
        print("Set AI_HEDGE_FUND_TELEGRAM_BOT_TOKEN and AI_HEDGE_FUND_TELEGRAM_CHAT_ID first.")
        return 2

    TelegramNotifier(config).send_trade_event(
        symbol="TEST",
        side="BUY",
        quantity=1,
        price=1.0,
        event="TELEGRAM_CONNECTIVITY_TEST",
        order_id="test-no-trade",
    )
    print("TELEGRAM TEST: PASS")
    print("Notification sent. No broker/order API was called.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
