"""Send paper-only extended-hours stop reminders for open Moomoo SIMULATE positions."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.config.telegram import telegram_config_from_env
from ai_henge_fund.portfolio.persistent_trade_state import PersistentTradeStateStore

NEW_YORK = ZoneInfo("America/New_York")
REMINDER_HOUR = {3: "PRE-MARKET", 15: "POST-MARKET"}


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def _current_window(now: datetime) -> str | None:
    if now.minute != 55:
        return None
    return REMINDER_HOUR.get(now.hour)


def _build_message(window: str, states) -> str:
    lines = [
        f"⚠️ PAPER EXTENDED-HOURS STOP ACTION — {window}",
        "Moomoo US SIMULATE does not support STOP or STOP_LIMIT orders.",
        "AI Henge Fund will not place a broker-side stop for these paper positions.",
        "Please manually perform the desired stop/protection action in Moomoo before the extended-hours window.",
        "",
    ]
    for state in states:
        side = "LONG" if state.side == "BUY" else "SHORT"
        stop = f"${state.stop_price:,.4f}" if state.stop_price is not None else "N/A"
        target = f"${state.target_price:,.4f}" if state.target_price is not None else "N/A"
        action = "SELL" if state.side == "BUY" else "BUY"
        lines.extend([
            f"{state.symbol} {side} | Qty: {state.quantity:g}",
            f"Entry: ${state.entry_price:,.4f} | Stop: {stop} | Target: {target}",
            f"Manual stop side: {action}",
            "",
        ])
    lines.append("Paper trading only — live trading is unaffected.")
    return "\n".join(lines)


def main() -> int:
    if not _truthy("MOOMOO_PAPER_TRADING_ENABLED") or _truthy("MOOMOO_LIVE_TRADING_ENABLED"):
        print("PAPER EXTENDED-HOURS REMINDER: SKIP (paper-only guard not satisfied)")
        return 0

    now = datetime.now(NEW_YORK)
    window = _current_window(now)
    if window is None:
        print(f"PAPER EXTENDED-HOURS REMINDER: NOOP ({now:%Y-%m-%d %H:%M:%S %Z})")
        return 0

    states = PersistentTradeStateStore().open_states()
    if not states:
        print(f"PAPER EXTENDED-HOURS REMINDER: NO OPEN PAPER POSITIONS ({window})")
        return 0

    notifier = TelegramNotifier(telegram_config_from_env())
    message = _build_message(window, states)
    notifier.send_text(message)
    print(f"PAPER EXTENDED-HOURS REMINDER: SENT ({window}) positions={len(states)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
