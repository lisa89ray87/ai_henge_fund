from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    timeout_seconds: float = 10.0

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)


class TelegramNotifier:
    """Small outbound notifier for trade-event alerts.

    This module sends notifications only. It has no broker or order capability.
    """

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config

    def send_trade_event(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        event: str = "PAPER_TRADE",
        order_id: str | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> None:
        if not self.config.enabled:
            return

        message = (
            "📈 AI Henge Fund Trade Event\n"
            f"Event: {event}\n"
            f"Symbol: {symbol.upper()}\n"
            f"Side: {side.upper()}\n"
            f"Quantity: {quantity:g}\n"
            f"Entry: ${price:,.4f}"
        )
        if stop_price is not None:
            message += f"\nStop: ${stop_price:,.4f}"
        if target_price is not None:
            message += f"\nTarget: ${target_price:,.4f}"
        if order_id:
            message += f"\nOrder ID: {order_id}"

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        response = httpx.post(
            url,
            json={"chat_id": self.config.chat_id, "text": message},
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
