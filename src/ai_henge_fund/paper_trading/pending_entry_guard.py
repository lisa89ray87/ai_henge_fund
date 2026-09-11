from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread

from ai_henge_fund.execution.moomoo_order_monitor import FILLED_ALL
from ai_henge_fund.paper_trading.engine import PaperTrade


_INSTALLED = False
_ORIGINAL_OPEN = None
_ORIGINAL_CLOSE = None
_ORIGINAL_RECONCILE = None


def install(cls):
    global _INSTALLED, _ORIGINAL_OPEN, _ORIGINAL_CLOSE, _ORIGINAL_RECONCILE
    if _INSTALLED:
        return
    _ORIGINAL_OPEN = cls.open
    _ORIGINAL_CLOSE = cls.close
    _ORIGINAL_RECONCILE = cls.reconcile_startup
    cls.open = _guarded_open
    cls.close = _guarded_close
    cls.reconcile_startup = _guarded_reconcile_startup
    _INSTALLED = True


def _ensure_runtime(self):
    if not hasattr(self, "_pending_entries"):
        self._pending_entries = {}
    if not hasattr(self, "_pending_entry_lock"):
        self._pending_entry_lock = Lock()


def _guarded_open(self, *, symbol, side, quantity, price, stop_price=None, target_price=None):
    _ensure_runtime(self)
    symbol = symbol.strip().upper()
    side = side.upper()
    with self._pending_entry_lock:
        pending = self._state.get(symbol)
        if pending is not None and pending.status == "PENDING" and pending.broker_order_id:
            return _resolve_pending(self, pending)
        for row in self.execution.list_open_orders():
            if row["symbol"] == symbol:
                self._state.upsert(symbol=symbol, side=side, quantity=float(quantity), entry_price=float(price),
                                   stop_price=stop_price, target_price=target_price,
                                   broker_order_id=row["order_id"], status="PENDING")
                _start_pending_watcher(self, symbol, row["order_id"], side, quantity, price, stop_price, target_price)
                self._notify_text(f"ENTRY ALREADY WORKING\n{symbol} {side} qty={int(quantity)} order={row['order_id']}\nNo duplicate entry submitted.")
                return _pending_result(self, symbol, row["order_id"], row["status"], price, stop_price, target_price)

    result = _ORIGINAL_OPEN(self, symbol=symbol, side=side, quantity=quantity, price=price,
                            stop_price=stop_price, target_price=target_price)
    if result.action == "PENDING" and result.broker_order_id:
        self._state.upsert(symbol=symbol, side=side, quantity=float(quantity), entry_price=float(price),
                           stop_price=stop_price, target_price=target_price,
                           broker_order_id=result.broker_order_id, status="PENDING")
        _start_pending_watcher(self, symbol, result.broker_order_id, side, quantity, price, stop_price, target_price)
        self._notify_text(f"ENTRY WORKING\n{symbol} {side} qty={int(quantity)} order={result.broker_order_id}\nEntry remains reserved until broker resolution.")
    return result


def _pending_result(self, symbol, order_id, status, price, stop_price, target_price):
    from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooLifecycleResult
    return MoomooLifecycleResult("PENDING", None, "Moomoo paper entry is still working; duplicate entry blocked",
                                 broker_order_id=order_id, broker_status=status, entry_price=price,
                                 stop_price=stop_price, target_price=target_price)


def _resolve_pending(self, state):
    status = self.monitor.get(state.broker_order_id)
    if status.status == FILLED_ALL and status.filled_quantity > 0:
        return _finalize_fill(self, state.symbol, state.side, state.broker_order_id, status.filled_quantity,
                              status.average_price or state.entry_price, state.stop_price, state.target_price)
    if status.status in {"CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"}:
        filled = float(status.filled_quantity or 0)
        if filled > 0:
            return _finalize_fill(self, state.symbol, state.side, state.broker_order_id, filled,
                                  status.average_price or state.entry_price, state.stop_price, state.target_price, partial=True)
        self._state.mark_closed(state.symbol)
        self._pending_entries.pop(state.symbol, None)
        self._notify_text(f"ENTRY CANCELLED\n{state.symbol} order={state.broker_order_id}")
        return _pending_result(self, state.symbol, state.broker_order_id, status.status,
                               state.entry_price, state.stop_price, state.target_price)
    _start_pending_watcher(self, state.symbol, state.broker_order_id, state.side, state.quantity,
                           state.entry_price, state.stop_price, state.target_price)
    return _pending_result(self, state.symbol, state.broker_order_id, status.status,
                           state.entry_price, state.stop_price, state.target_price)


def _start_pending_watcher(self, symbol, order_id, side, quantity, price, stop_price, target_price):
    _ensure_runtime(self)
    existing = self._pending_entries.get(symbol)
    if existing is not None and existing[1].is_alive():
        return
    stop_event = Event()
    thread = Thread(target=_watch_pending_entry,
                    args=(self, symbol, order_id, side, quantity, price, stop_price, target_price, stop_event),
                    daemon=True)
    self._pending_entries[symbol] = (stop_event, thread)
    thread.start()


def _watch_pending_entry(self, symbol, order_id, side, quantity, price, stop_price, target_price, stop_event):
    while not stop_event.is_set():
        try:
            status = self.monitor.get(order_id)
            if status.status == FILLED_ALL and status.filled_quantity > 0:
                _finalize_fill(self, symbol, side, order_id, status.filled_quantity,
                               status.average_price or price, stop_price, target_price)
                return
            if status.status in {"CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"}:
                filled = float(status.filled_quantity or 0)
                if filled > 0:
                    _finalize_fill(self, symbol, side, order_id, filled,
                                   status.average_price or price, stop_price, target_price, partial=True)
                else:
                    self._state.mark_closed(symbol)
                    self._notify_text(f"ENTRY CANCELLED\n{symbol} order={order_id}")
                return
        except Exception as exc:
            print(f"ENTRY WATCH {symbol}: {exc}")
        stop_event.wait(2.0)


def _finalize_fill(self, symbol, side, order_id, filled_quantity, fill_price, stop_price, target_price, partial=False):
    _ensure_runtime(self)
    existing = self.positions.get(symbol)
    if existing is not None:
        self._state.upsert(symbol=symbol, side=side, quantity=abs(existing.quantity), entry_price=existing.average_price,
                           stop_price=existing.stop_price, target_price=existing.target_price,
                           broker_order_id=order_id, status="OPEN")
        return _pending_result(self, symbol, order_id, FILLED_ALL, fill_price, stop_price, target_price)
    qty = float(filled_quantity)
    signed_quantity = qty if side == "BUY" else -qty
    trade = PaperTrade(trade_id=f"moomoo-{order_id}", symbol=symbol, side=side, quantity=qty,
                       price=float(fill_price), executed_at=datetime.now(timezone.utc), status=FILLED_ALL,
                       metadata={"broker": "moomoo", "trading_environment": "SIMULATE", "broker_order_id": order_id,
                                 "broker_status": "FILLED_PART" if partial else FILLED_ALL, "entry_price": float(fill_price),
                                 "stop_price": stop_price, "target_price": target_price, "position_size_source": "ai"})
    self.positions.open_signed(symbol, signed_quantity, float(fill_price), stop_price=stop_price, target_price=target_price)
    self._state.upsert(symbol=symbol, side=side, quantity=qty, entry_price=float(fill_price), stop_price=stop_price,
                       target_price=target_price, broker_order_id=order_id, status="OPEN")
    self._state.record_open(trade_id=trade.trade_id, symbol=symbol, side=side, quantity=qty, entry_price=float(fill_price),
                            stop_price=stop_price, target_price=target_price, broker_entry_order_id=order_id,
                            opened_at=trade.executed_at)
    self._notify(trade, "MOOMOO_PAPER_PARTIAL_FILL" if partial else "MOOMOO_PAPER_FILL",
                 stop_price=stop_price, target_price=target_price)
    target_order_id = None
    target_ok = True
    if target_price is not None and target_price > 0:
        target_order_id = self._arm_target(symbol, side, int(qty), float(target_price), notify=True)
        target_ok = target_order_id is not None
    if (stop_price is not None and stop_price > 0) or target_order_id:
        self._start_exit_watcher(symbol, side, int(qty), float(stop_price or 0.0), target_order_id)
    with self._pending_entry_lock:
        pending = self._pending_entries.pop(symbol, None)
        if pending is not None:
            pending[0].set()
    reason = "Moomoo paper entry filled; exit protection armed"
    if partial:
        reason = "Moomoo paper entry partially filled; duplicate entry blocked and protection armed"
    elif not target_ok:
        reason = "Moomoo paper entry filled; STOP watcher armed but TARGET verification failed"
    from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooLifecycleResult
    return MoomooLifecycleResult("OPEN", trade, reason, broker_order_id=order_id,
                                 broker_status=trade.metadata["broker_status"], entry_price=float(fill_price),
                                 stop_price=stop_price, target_price=target_price)


def _guarded_reconcile_startup(self):
    """Reconcile entries, then enforce Moomoo's signed position as direction truth."""
    _ensure_runtime(self)
    symbols = set()
    try:
        symbols.update(row["symbol"] for row in self.execution.list_open_orders())
        broker_positions = self.execution.list_positions()
        symbols.update(row["symbol"] for row in broker_positions)
    except Exception as exc:
        print(f"RECONCILE ENTRY discovery failed: {exc}")
        broker_positions = []
    for symbol in symbols:
        try:
            state = self._state.get(symbol)
            if state is not None and state.status == "PENDING" and state.broker_order_id:
                _resolve_pending(self, state)
        except Exception as exc:
            print(f"RECONCILE ENTRY {symbol}: {exc}")

    result = _ORIGINAL_RECONCILE(self)

    # The broker's signed quantity is authoritative. Preserve saved protection metadata.
    try:
        broker_positions = self.execution.list_positions()
        for row in broker_positions:
            symbol = row["symbol"]
            broker_qty = float(row.get("quantity", 0.0) or 0.0)
            if broker_qty == 0:
                continue
            state = self._state.get(symbol)
            if state is None:
                self._notify_text(f"⚠️ POSITION STATE MISSING\n{symbol}: broker position {_qty_text(abs(broker_qty))} requires manual review; protection history unavailable.")
                continue

            broker_side = "BUY" if broker_qty > 0 else "SELL"
            saved_side = state.side.upper()
            if broker_side != saved_side:
                self._notify_text(
                    f"⚠️ POSITION STATE MISMATCH\n{symbol}: saved {saved_side}, broker {broker_side} "
                    f"({_qty_text(abs(broker_qty))}). Broker direction is authoritative."
                )

            self.positions.restore(symbol, broker_qty, float(row["average_price"]),
                                   stop_price=state.stop_price, target_price=state.target_price)
            self._state.upsert(symbol=symbol, side=broker_side, quantity=abs(broker_qty),
                               entry_price=float(row["average_price"]), stop_price=state.stop_price,
                               target_price=state.target_price, broker_order_id=state.broker_order_id,
                               status="OPEN")
    except Exception as exc:
        print(f"RECONCILE POSITION AUTHORITY failed: {exc}")
    return result


def _qty_text(value: float) -> str:
    return f"{value:g}"


def _guarded_close(self):
    _ensure_runtime(self)
    for stop_event, _thread in list(self._pending_entries.values()):
        stop_event.set()
    self._pending_entries.clear()
    return _ORIGINAL_CLOSE(self)
