"""Send an end-of-day summary for the Moomoo US SIMULATE paper session."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.config.telegram import day_summary_telegram_config_from_env
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_henge_fund.portfolio.persistent_trade_state import PersistentTradeStateStore

ET = ZoneInfo("America/New_York")
FILLED = {"FILLED_ALL", "FILLED"}


def _day_key(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ET).date().isoformat()
    except ValueError:
        return value[:10]


def _money(value: float | None) -> str:
    return "N/A" if value is None else f"${value:,.2f}"


def _classify_exit(entry_side: str, exit_price: float, stop: float | None, target: float | None) -> str:
    if target is not None:
        if abs(exit_price - target) <= max(0.01, abs(target) * 0.002):
            return "TARGET"
    if stop is not None:
        if (entry_side == "BUY" and exit_price <= stop * 1.002) or (entry_side == "SELL" and exit_price >= stop * 0.998):
            return "STOP"
    return "CLOSE"


def _realized_pnl(entry_side: str, entry_price: float, exit_price: float, quantity: float) -> float:
    return (exit_price - entry_price) * quantity if entry_side == "BUY" else (entry_price - exit_price) * quantity


def build_summary() -> str:
    execution = MoomooPaperExecution()
    state_store = PersistentTradeStateStore()
    try:
        today = datetime.now(ET).date().isoformat()
        orders = [row for row in execution.list_order_history() if _day_key(row["create_time"]) == today or _day_key(row["updated_time"]) == today]
        filled = [row for row in orders if row["status"] in FILLED and row["filled_quantity"] > 0]
        states = {state.symbol: state for state in state_store.open_states()}
        # CLOSED rows are intentionally retained by the state store so their entry,
        # stop and target levels remain available for today's exit classification.
        all_states = {}
        for symbol in {row["symbol"] for row in filled} | set(states):
            state = state_store.get(symbol)
            if state is not None:
                all_states[symbol] = state

        entries: list[str] = []
        exits: list[str] = []
        pnl_total = 0.0
        pnl_count = 0

        for symbol, state in sorted(all_states.items()):
            symbol_fills = [row for row in filled if row["symbol"] == symbol]
            if not symbol_fills:
                continue
            entry_side = state.side
            entry = state.entry_price
            # A same-day fill at the saved entry price is treated as the AI entry.
            entry_rows = [row for row in symbol_fills if row["side"] == entry_side and abs(row["filled_price"] - entry) <= max(0.01, entry * 0.002)]
            if entry_rows:
                row = entry_rows[-1]
                entries.append(
                    f"• {symbol} {entry_side} {row['filled_quantity']:g} @ {_money(row['filled_price'])} "
                    f"| stop {_money(state.stop_price)} | target {_money(state.target_price)}"
                )

            exit_side = "SELL" if entry_side == "BUY" else "BUY"
            exit_rows = [row for row in symbol_fills if row["side"] == exit_side]
            for row in exit_rows:
                exit_price = row["filled_price"]
                quantity = row["filled_quantity"]
                reason = _classify_exit(entry_side, exit_price, state.stop_price, state.target_price)
                pnl = _realized_pnl(entry_side, entry, exit_price, quantity)
                pnl_total += pnl
                pnl_count += 1
                exits.append(
                    f"• {symbol} {reason} {quantity:g} @ {_money(exit_price)} "
                    f"| P/L {_money(pnl)} | entry {_money(entry)}"
                )

        current_positions = execution.list_positions()
        handoffs: list[str] = []
        for row in current_positions:
            state = all_states.get(row["symbol"]) or state_store.get(row["symbol"])
            if state is None:
                handoffs.append(f"• {row['symbol']} — target/stop history unavailable; manual review")
                continue
            side = "LONG" if state.side == "BUY" else "SHORT"
            handoffs.append(
                f"• {row['symbol']} {side} {row['quantity']:g} | entry {_money(row['average_price'])} "
                f"| handoff target {_money(state.target_price)} | stop {_money(state.stop_price)}"
            )

        message = [
            "📊 AI Henge Fund — PAPER DAY SUMMARY",
            f"Date: {today} (US/Eastern)",
            "Environment: Moomoo US SIMULATE / PAPER",
            "Live trading: DISABLED",
            "",
            f"🟢 AI entries ({len(entries)})",
            *(entries or ["• None"]),
            "",
            f"🔴 Stops / targets / closes ({len(exits)})",
            *(exits or ["• None"]),
            "",
            f"💰 Realized P/L: {_money(pnl_total)}" + (f" across {pnl_count} exit(s)" if pnl_count else ""),
            "",
            f"🌙 Overnight handoff ({len(handoffs)})",
            *(handoffs or ["• None — no open paper positions"]),
            "",
            "AI Henge Fund stops agent-side monitoring after the regular session; handed-off positions require manual extended-hours monitoring.",
        ]
        return "\n".join(message)
    finally:
        execution.close()


def main() -> int:
    notifier = TelegramNotifier(day_summary_telegram_config_from_env())
    if not notifier.config.enabled:
        print("DAY SUMMARY TELEGRAM: SKIPPED (dedicated bot/chat secrets are not configured)")
        return 0
    try:
        message = build_summary()
        notifier.send_text(message)
        print("DAY SUMMARY TELEGRAM: PASS")
        return 0
    except Exception as exc:
        print(f"DAY SUMMARY TELEGRAM: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
