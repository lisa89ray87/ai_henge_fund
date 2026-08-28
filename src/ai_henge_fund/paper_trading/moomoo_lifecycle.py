from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Thread
from time import sleep

from moomoo import OpenQuoteContext

from ai_henge_fund.alerts.telegram import TelegramNotifier
from ai_henge_fund.execution.moomoo_order_monitor import FILLED_ALL, MoomooPaperOrderMonitor
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution
from ai_henge_fund.paper_trading.engine import PaperTrade
from ai_henge_fund.portfolio.manager import PositionManager
from ai_henge_fund.portfolio.persistent_trade_state import PersistentTradeStateStore


@dataclass(frozen=True)
class MoomooLifecycleResult:
    action: str
    trade: PaperTrade | None
    reason: str
    broker_order_id: str | None = None
    broker_status: str | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


class MoomooPaperTradeLifecycle:
    """Execute and resume the strategy lifecycle through Moomoo US SIMULATE only."""

    def __init__(self, execution, monitor, positions, telegram=None, *, fill_timeout_seconds=30, exit_poll_seconds=2.0):
        self.execution = execution
        self.monitor = monitor
        self.positions = positions
        self.telegram = telegram
        self.fill_timeout_seconds = fill_timeout_seconds
        self.exit_poll_seconds = exit_poll_seconds
        self._watchers: dict[str, tuple[Event, Thread]] = {}
        self._target_orders: dict[str, str] = {}
        self._quote = OpenQuoteContext(host="127.0.0.1", port=11111)
        self._state = PersistentTradeStateStore()

    def close(self) -> None:
        for stop_event, _thread in list(self._watchers.values()):
            stop_event.set()
        self._watchers.clear()
        self._quote.close()
        self.execution.close()
        self.monitor.close()

    def reconcile_startup(self) -> int:
        """Rebuild in-memory positions and restore target orders and stop watchers."""
        broker_positions = self.execution.list_positions()
        broker_by_symbol = {row["symbol"]: row for row in broker_positions}
        working_orders = self.execution.list_open_orders()
        open_states = {state.symbol: state for state in self._state.open_states()}

        for row in broker_positions:
            symbol = row["symbol"]
            state = open_states.get(symbol)
            if state is None:
                self.positions.restore(symbol, row["quantity"], row["average_price"])
                print(f"RECONCILE {symbol}: broker position found without saved trade state")
                self._notify_text(
                    f"⚠️ POSITION RECONCILIATION\n{symbol}: existing Moomoo paper position found, "
                    "but AI Henge Fund has no saved entry/target/stop history. Manual review required."
                )
                continue

            signed_qty = abs(row["quantity"]) if state.side == "BUY" else -abs(row["quantity"])
            self.positions.restore(
                symbol, signed_qty, row["average_price"],
                stop_price=state.stop_price, target_price=state.target_price,
            )
            print(
                f"RECONCILE {symbol}: {state.side} qty={abs(signed_qty):g} "
                f"entry=${row['average_price']:,.4f} target={state.target_price} stop={state.stop_price}"
            )

            target_order_id = self._matching_exit_order_id(working_orders, symbol, state.target_price, state.side)
            if target_order_id:
                self._target_orders[symbol] = target_order_id
                print(f"RECONCILE {symbol}: target order found {target_order_id} @ ${state.target_price:,.4f}")
            elif state.target_price and state.target_price > 0:
                target_side = "SELL" if signed_qty > 0 else "BUY"
                try:
                    order = self.execution.place_limit(
                        symbol=symbol, side=target_side, quantity=int(abs(signed_qty)), price=float(state.target_price)
                    )
                    target_order_id = order.order_id
                    self._target_orders[symbol] = target_order_id
                    print(f"RECONCILE {symbol}: target order restored and verified {order.order_id} @ ${state.target_price:,.4f}")
                    self._notify_text(
                        f"🎯 EXIT PROTECTION RESTORED\n{symbol} {target_side} {int(abs(signed_qty))} @ ${state.target_price:,.4f}\n"
                        f"Target order ID: {target_order_id}\nStatus: {order.status}"
                    )
                except Exception as exc:
                    print(f"RECONCILE {symbol}: target restoration failed: {exc}")
                    self._notify_exit_protection_failed(symbol, target_side, int(abs(signed_qty)), state.target_price, str(exc))

            if state.stop_price and not self._has_active_stop_watcher(symbol):
                self._start_exit_watcher(
                    symbol,
                    state.side,
                    int(abs(signed_qty)),
                    state.stop_price,
                    target_order_id,
                )
                print(f"RECONCILE {symbol}: stop watcher restored @ ${state.stop_price:,.4f}")

        for symbol in open_states:
            if symbol not in broker_by_symbol:
                self._state.mark_closed(symbol)
                print(f"RECONCILE {symbol}: saved position is no longer present in Moomoo; marked CLOSED")

        count = len(broker_positions)
        self._notify_text(
            f"🔄 SESSION RESUMED\nExisting paper positions: {count}\n"
            f"Saved trade states checked: {len(open_states)}\n"
            "Moomoo is the position source of truth; unmatched positions require manual review."
        )
        return count

    def overnight_handoff(self) -> None:
        """Stop agent-side monitoring and hand extended-hours responsibility to the user."""
        for position in self.positions.all():
            target_order_id = self._target_orders.pop(position.symbol, None)
            if target_order_id:
                try:
                    self.execution.cancel(target_order_id)
                except Exception as exc:
                    print(f"HANDOFF {position.symbol}: target cancellation failed: {exc}")
            self._stop_watcher(position.symbol)
            side = "LONG" if position.quantity > 0 else "SHORT"
            target = f"${position.target_price:,.4f}" if position.target_price is not None else "N/A"
            stop = f"${position.stop_price:,.4f}" if position.stop_price is not None else "N/A"
            self._notify_text(
                f"🌙 OVERNIGHT HANDOFF — {position.symbol} {side}\n"
                f"Entry: ${position.average_price:,.4f}\n"
                f"Target: {target}\n"
                f"Stop: {stop}\n"
                "AI Henge Fund will NOT monitor pre-market, after-hours, or overnight. "
                "Please monitor the position and create any extended-hours protection manually."
            )

    def open(self, *, symbol, side, quantity, price, stop_price=None, target_price=None):
        side = side.upper()
        symbol = symbol.strip().upper()
        if side not in {"BUY", "SELL"}:
            return MoomooLifecycleResult("WAIT", None, "Unsupported opening side")
        if quantity <= 0 or price <= 0:
            return MoomooLifecycleResult("WAIT", None, "Invalid quantity or price")
        if self.positions.get(symbol) is not None:
            return MoomooLifecycleResult("WAIT", None, "Position already open")

        requested_quantity = int(quantity)
        if float(requested_quantity) != float(quantity):
            return MoomooLifecycleResult("WAIT", None, "Moomoo stock paper execution requires whole-share quantity")

        order = self.execution.place_limit(symbol=symbol, side=side, quantity=requested_quantity, price=price)
        status = self.monitor.wait_for_terminal(order.order_id, timeout_seconds=self.fill_timeout_seconds)
        if status.status != FILLED_ALL or status.filled_quantity < requested_quantity:
            return MoomooLifecycleResult(
                "PENDING", None, "Moomoo paper order submitted but not fully filled",
                broker_order_id=order.order_id, broker_status=status.status,
                entry_price=price, stop_price=stop_price, target_price=target_price,
            )

        fill_price = status.average_price or price
        signed_quantity = status.filled_quantity if side == "BUY" else -status.filled_quantity
        trade = PaperTrade(
            trade_id=f"moomoo-{order.order_id}", symbol=symbol, side=side,
            quantity=status.filled_quantity, price=fill_price,
            executed_at=datetime.now(timezone.utc), status=FILLED_ALL,
            metadata={
                "broker": "moomoo", "trading_environment": "SIMULATE",
                "broker_order_id": order.order_id, "broker_status": status.status,
                "entry_price": fill_price, "stop_price": stop_price, "target_price": target_price,
                "position_size_source": "ai",
            },
        )
        self.positions.open_signed(symbol, signed_quantity, fill_price, stop_price=stop_price, target_price=target_price)
        self._state.upsert(
            symbol=symbol, side=side, quantity=status.filled_quantity, entry_price=fill_price,
            stop_price=stop_price, target_price=target_price, broker_order_id=order.order_id,
        )
        self._notify(trade, "MOOMOO_PAPER_FILL", stop_price=stop_price, target_price=target_price)

        target_order_id = None
        target_protection_ok = True
        if target_price is not None and target_price > 0:
            target_side = "SELL" if side == "BUY" else "BUY"
            try:
                target_order = self.execution.place_limit(
                    symbol=symbol, side=target_side, quantity=int(status.filled_quantity), price=float(target_price)
                )
                target_order_id = target_order.order_id
                self._target_orders[symbol] = target_order_id
                print(f"  paper target order VERIFIED: {target_order_id} @ ${float(target_price):,.4f} status={target_order.status}")
                self._notify_text(
                    f"🎯 TARGET ORDER ARMED\n{symbol} {target_side} {int(status.filled_quantity)} @ ${float(target_price):,.4f}\n"
                    f"Target order ID: {target_order_id}\nStatus: {target_order.status}"
                )
            except Exception as exc:
                target_protection_ok = False
                print(f"  paper target order FAILED VERIFICATION: {exc}")
                self._notify_exit_protection_failed(
                    symbol, target_side, int(status.filled_quantity), float(target_price), str(exc)
                )

        if stop_price is not None and stop_price > 0:
            self._start_exit_watcher(symbol, side, int(status.filled_quantity), float(stop_price), target_order_id)
            print(f"  paper stop watcher: ${float(stop_price):,.4f}")

        reason = "Moomoo paper order fully filled; exit protection armed" if target_protection_ok else "Moomoo paper entry filled; STOP watcher armed but TARGET order verification failed"
        return MoomooLifecycleResult(
            "OPEN", trade, reason,
            broker_order_id=order.order_id, broker_status=status.status,
            entry_price=fill_price, stop_price=stop_price, target_price=target_price,
        )

    def close_position(self, *, symbol, price):
        symbol = symbol.strip().upper()
        position = self.positions.get(symbol)
        if position is None:
            return MoomooLifecycleResult("WAIT", None, "No open position")
        self._stop_watcher(symbol)
        target_order_id = self._target_orders.pop(symbol, None)
        if target_order_id:
            try:
                self.execution.cancel(target_order_id)
            except Exception as exc:
                print(f"CLOSE {symbol}: target cancellation failed: {exc}")
        closing_side = "SELL" if position.quantity > 0 else "BUY"
        quantity = abs(position.quantity)
        if float(int(quantity)) != float(quantity):
            return MoomooLifecycleResult("WAIT", None, "Moomoo stock paper execution requires whole-share quantity")
        order = self.execution.place_limit(symbol=symbol, side=closing_side, quantity=int(quantity), price=price)
        status = self.monitor.wait_for_terminal(order.order_id, timeout_seconds=self.fill_timeout_seconds)
        if status.status != FILLED_ALL or status.filled_quantity < quantity:
            return MoomooLifecycleResult("PENDING", None, "Moomoo paper close order submitted but not fully filled", broker_order_id=order.order_id, broker_status=status.status)
        fill_price = status.average_price or price
        trade = PaperTrade(
            trade_id=f"moomoo-{order.order_id}", symbol=symbol, side=closing_side,
            quantity=status.filled_quantity, price=fill_price, executed_at=datetime.now(timezone.utc), status=FILLED_ALL,
            metadata={"broker": "moomoo", "trading_environment": "SIMULATE", "broker_order_id": order.order_id, "broker_status": status.status},
        )
        self.positions.close(symbol)
        self._state.mark_closed(symbol)
        self._notify(trade, "MOOMOO_PAPER_CLOSE_FILL")
        return MoomooLifecycleResult("CLOSE", trade, "Moomoo paper close order fully filled", broker_order_id=order.order_id, broker_status=status.status)

    def _start_exit_watcher(self, symbol, entry_side, quantity, stop_price, target_order_id):
        self._stop_watcher(symbol)
        stop_event = Event()
        thread = Thread(target=self._watch_exit, args=(symbol, entry_side, quantity, stop_price, target_order_id, stop_event), daemon=True)
        self._watchers[symbol] = (stop_event, thread)
        thread.start()

    def _has_active_stop_watcher(self, symbol):
        watcher = self._watchers.get(symbol)
        return watcher is not None and watcher[1].is_alive() and not watcher[0].is_set()

    def _stop_watcher(self, symbol):
        watcher = self._watchers.pop(symbol, None)
        if watcher is not None:
            watcher[0].set()

    def _watch_exit(self, symbol, entry_side, quantity, stop_price, target_order_id, stop_event):
        while not stop_event.is_set():
            try:
                if target_order_id:
                    target_status = self.monitor.get(target_order_id)
                    if target_status.status == FILLED_ALL:
                        fill_price = target_status.average_price or stop_price
                        trade = self._exit_trade(symbol, "SELL" if entry_side == "BUY" else "BUY", target_status.filled_quantity, fill_price, target_order_id)
                        self._notify(trade, "MOOMOO_PAPER_TARGET_FILL", target_price=fill_price)
                        return
                    if target_status.status in {"CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"}:
                        target_order_id = None
                        self._notify_text(
                            f"⚠️ TARGET ORDER LOST\n{symbol}: target order {target_order_id or 'unknown'} became inactive. "
                            "Stop watcher remains active."
                        )

                ret, data = self._quote.get_market_snapshot([symbol])
                if ret != 0 or data.empty:
                    sleep(self.exit_poll_seconds)
                    continue
                last_price = float(data.iloc[0].get("last_price", 0.0) or 0.0)
                triggered = last_price <= stop_price if entry_side == "BUY" else last_price >= stop_price
                if triggered:
                    if target_order_id:
                        try:
                            self.execution.cancel(target_order_id)
                        except Exception as exc:
                            print(f"EXIT {symbol}: target cancellation failed: {exc}")
                    exit_side = "SELL" if entry_side == "BUY" else "BUY"
                    exit_order = self.execution.place_market(symbol=symbol, side=exit_side, quantity=quantity)
                    exit_status = self.monitor.wait_for_terminal(exit_order.order_id, timeout_seconds=self.fill_timeout_seconds)
                    if exit_status.status == FILLED_ALL:
                        fill_price = exit_status.average_price or last_price
                        trade = self._exit_trade(symbol, exit_side, exit_status.filled_quantity, fill_price, exit_order.order_id)
                        self._notify(trade, "MOOMOO_PAPER_STOP_FILL", stop_price=stop_price)
                    else:
                        print(f"EXIT {symbol}: stop market order did not fully fill: {exit_status.status}")
                    return
            except Exception as exc:
                print(f"EXIT {symbol}: watcher error: {exc}")
            sleep(self.exit_poll_seconds)

    def _exit_trade(self, symbol, side, quantity, price, order_id):
        trade = PaperTrade(
            trade_id=f"moomoo-{order_id}", symbol=symbol, side=side, quantity=quantity, price=price,
            executed_at=datetime.now(timezone.utc), status=FILLED_ALL,
            metadata={"broker": "moomoo", "trading_environment": "SIMULATE", "broker_order_id": order_id},
        )
        self.positions.close(symbol)
        self._target_orders.pop(symbol, None)
        self._state.mark_closed(symbol)
        return trade

    @staticmethod
    def _has_matching_exit_order(orders, symbol, target_price, entry_side) -> bool:
        if target_price is None:
            return False
        exit_side = "SELL" if entry_side == "BUY" else "BUY"
        return any(
            row["symbol"] == symbol
            and row["side"].endswith(exit_side)
            and abs(row["price"] - target_price) < 1e-6
            for row in orders
        )

    @staticmethod
    def _matching_exit_order_id(orders, symbol, target_price, entry_side) -> str | None:
        if target_price is None:
            return None
        exit_side = "SELL" if entry_side == "BUY" else "BUY"
        for row in orders:
            if row["symbol"] == symbol and row["side"].endswith(exit_side) and abs(row["price"] - target_price) < 1e-6:
                return row["order_id"]
        return None

    def _notify(self, trade, event, *, stop_price=None, target_price=None):
        if self.telegram is not None:
            self.telegram.send_trade_event(
                symbol=trade.symbol, side=trade.side, quantity=trade.quantity, price=trade.price,
                event=event, order_id=trade.trade_id, stop_price=stop_price, target_price=target_price,
            )

    def _notify_text(self, message):
        if self.telegram is not None:
            try:
                self.telegram.send_text(message)
            except Exception as exc:
                print(f"TELEGRAM: notification failed: {exc}")

    def _notify_exit_protection_failed(self, symbol, side, quantity, target_price, reason):
        self._notify_text(
            f"🚨 EXIT PROTECTION FAILED\n"
            f"Symbol: {symbol}\n"
            f"Target side: {side}\n"
            f"Quantity: {quantity:g}\n"
            f"Target: ${target_price:,.4f}\n"
            f"Reason: {reason}\n"
            "The paper position remains open. STOP watcher is active if configured. "
            "Manual review required."
        )
