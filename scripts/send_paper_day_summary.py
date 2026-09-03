"""Send an end-of-day summary for the Moomoo US SIMULATE paper session."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.config.telegram import day_summary_telegram_config_from_env
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_henge_fund.portfolio.persistent_trade_state import PersistentTradeStateStore, TradeJournalEntry

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
    return "N/A" if value is None else f"{value:,.2f}"


def _qty(value: float) -> str:
    return f"{value:g}"


def _classify_exit(entry_side: str, exit_price: float, stop: float | None, target: float | None) -> str:
    if target is not None and abs(exit_price - target) <= max(0.01, abs(target) * 0.002):
        return "TARGET"
    if stop is not None:
        if (entry_side == "BUY" and exit_price <= stop * 1.002) or (entry_side == "SELL" and exit_price >= stop * 0.998):
            return "STOP"
    return "CLOSE"


def _realized_pnl(entry_side: str, entry_price: float, exit_price: float, quantity: float) -> float:
    return (exit_price - entry_price) * quantity if entry_side == "BUY" else (entry_price - exit_price) * quantity


def format_trade_block(symbol: str, *, side: str, quantity: float, entry_price: float,
                       stop_price: float | None, target_price: float | None,
                       exit_quantity: float | None, exit_price: float | None,
                       pnl: float | None, reason: str | None) -> str:
    """Render one complete lifecycle in the compact Telegram layout."""
    lines = [symbol, f"  Entry {_qty(quantity)} @ {_money(entry_price)}"]
    if target_price is not None:
        lines.append(f"  Target {_money(target_price)}")
    if stop_price is not None:
        lines.append(f"  Stop {_money(stop_price)}")
    if exit_price is not None:
        lines.append(f"  Exit {_qty(exit_quantity or quantity)} @ {_money(exit_price)}")
        lines.append(f"  P/L {'+' if (pnl or 0) >= 0 else ''}{_money(pnl)}")
        lines.append(f"  Reason {reason or 'CLOSE'}")
    return "\n".join(lines)


def _journal_block(entry: TradeJournalEntry) -> str:
    return format_trade_block(
        entry.symbol, side=entry.side, quantity=entry.quantity, entry_price=entry.entry_price,
        stop_price=entry.stop_price, target_price=entry.target_price,
        exit_quantity=entry.exit_quantity, exit_price=entry.exit_price,
        pnl=entry.realized_pnl, reason=entry.exit_reason,
    )


def _legacy_blocks(execution, state_store, filled) -> tuple[list[str], float, int]:
    """Fallback for trades made before the trade-instance journal was introduced."""
    blocks: list[str] = []
    pnl_total = 0.0
    pnl_count = 0
    for symbol in sorted({row["symbol"] for row in filled}):
        state = state_store.get(symbol)
        if state is None:
            continue
        symbol_fills = [row for row in filled if row["symbol"] == symbol]
        entry_rows = [
            row for row in symbol_fills
            if row["side"] == state.side
            and abs(row["filled_price"] - state.entry_price) <= max(0.01, state.entry_price * 0.002)
        ]
        exit_side = "SELL" if state.side == "BUY" else "BUY"
        exit_rows = [row for row in symbol_fills if row["side"] == exit_side]
        entry_row = entry_rows[-1] if entry_rows else None
        entry_qty = entry_row["filled_quantity"] if entry_row else abs(state.quantity)
        entry_price = entry_row["filled_price"] if entry_row else state.entry_price
        if not entry_row and not exit_rows:
            continue
        if exit_rows:
            row = exit_rows[-1]
            reason = _classify_exit(state.side, row["filled_price"], state.stop_price, state.target_price)
            pnl = _realized_pnl(state.side, entry_price, row["filled_price"], row["filled_quantity"])
            pnl_total += pnl
            pnl_count += 1
            blocks.append(format_trade_block(
                symbol, side=state.side, quantity=entry_qty, entry_price=entry_price,
                stop_price=state.stop_price, target_price=state.target_price,
                exit_quantity=row["filled_quantity"], exit_price=row["filled_price"], pnl=pnl, reason=reason,
            ))
        else:
            blocks.append(format_trade_block(
                symbol, side=state.side, quantity=entry_qty, entry_price=entry_price,
                stop_price=state.stop_price, target_price=state.target_price,
                exit_quantity=None, exit_price=None, pnl=None, reason=None,
            ))
    return blocks, pnl_total, pnl_count


def build_summary() -> str:
    execution = MoomooPaperExecution()
    state_store = PersistentTradeStateStore()
    try:
        today = datetime.now(ET).date()
        day_start = datetime.combine(today, time.min, tzinfo=ET)
        day_end = day_start + timedelta(days=1)
        orders = [
            row for row in execution.list_order_history()
            if _day_key(row["create_time"]) == today.isoformat() or _day_key(row["updated_time"]) == today.isoformat()
        ]
        filled = [row for row in orders if row["status"] in FILLED and row["filled_quantity"] > 0]

        journal = state_store.journal_for_day(day_start, day_end)
        completed = [entry for entry in journal if entry.exit_price is not None and entry.exit_quantity]
        blocks = [_journal_block(entry) for entry in completed]
        pnl_total = sum(entry.realized_pnl or 0.0 for entry in completed)
        pnl_count = len(completed)

        journal_symbols = {entry.symbol for entry in journal}
        legacy_filled = [row for row in filled if row["symbol"] not in journal_symbols]
        legacy_blocks, legacy_pnl, legacy_count = _legacy_blocks(execution, state_store, legacy_filled)
        blocks.extend(legacy_blocks)
        pnl_total += legacy_pnl
        pnl_count += legacy_count

        current_positions = execution.list_positions()
        handoffs: list[str] = []
        for row in current_positions:
            state = state_store.get(row["symbol"])
            if state is None:
                handoffs.append(f"{row['symbol']}\n  Target/Stop history unavailable\n  Manual review required")
                continue
            side = "LONG" if state.side == "BUY" else "SHORT"
            handoffs.append(
                f"{row['symbol']}\n"
                f"  {side} {_qty(row['quantity'])}\n"
                f"  Entry {_qty(row['quantity'])} @ {_money(row['average_price'])}\n"
                + (f"  Target {_money(state.target_price)}\n" if state.target_price is not None else "")
                + (f"  Stop {_money(state.stop_price)}" if state.stop_price is not None else "  Stop N/A")
            )

        message = [
            "📊 AI Henge Fund — PAPER DAY SUMMARY",
            today.strftime("%m/%d"),
            "Environment: Moomoo US SIMULATE / PAPER",
            "Live trading: DISABLED",
            "",
            "📈 TRADES",
            "",
        ]
        if blocks:
            for index, block in enumerate(blocks):
                if index:
                    message.append("")
                message.append(block)
        else:
            message.append("  None")

        message.extend([
            "",
            f"💰 Realized P/L: {'+' if pnl_total >= 0 else ''}{_money(pnl_total)}"
            + (f" across {pnl_count} exit(s)" if pnl_count else ""),
            "",
            f"🌙 OVERNIGHT HANDOFF ({len(handoffs)})",
        ])
        if handoffs:
            for index, block in enumerate(handoffs):
                if index:
                    message.append("")
                message.append(block)
        else:
            message.append("  None — no open paper positions")

        message.extend([
            "",
            "AI Henge Fund stops agent-side monitoring after the regular session; handed-off positions require manual extended-hours monitoring.",
        ])
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
