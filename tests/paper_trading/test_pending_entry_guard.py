from dataclasses import dataclass

from ai_henge_fund.paper_trading.pending_entry_guard import _guarded_open


@dataclass
class FakeState:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    broker_order_id: str
    status: str


class FakeStateStore:
    def __init__(self, state=None):
        self.state = state
        self.upserts = []
        self.closed = []

    def get(self, symbol):
        return self.state if self.state and self.state.symbol == symbol else None

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)
        self.state = FakeState(**kwargs, updated_at=None)

    def mark_closed(self, symbol):
        self.closed.append(symbol)


class FakeExecution:
    def __init__(self, rows=None):
        self.rows = rows or []

    def list_open_orders(self):
        return list(self.rows)


class FakeMonitor:
    def __init__(self, status):
        self.status = status

    def get(self, order_id):
        return self.status


class FakePositions:
    def get(self, symbol):
        return None


class FakeLifecycle:
    def __init__(self, state=None, broker_rows=None, status=None):
        self._state = FakeStateStore(state)
        self.execution = FakeExecution(broker_rows)
        self.monitor = FakeMonitor(status)
        self.positions = FakePositions()
        self._pending_entries = {}
        self.notifications = []
        self.exit_watchers = []

    def _notify_text(self, message):
        self.notifications.append(message)

    def _notify(self, *args, **kwargs):
        pass

    def _arm_target(self, *args, **kwargs):
        return None

    def _start_exit_watcher(self, *args, **kwargs):
        self.exit_watchers.append(args)


def test_existing_pending_entry_blocks_duplicate_order():
    lifecycle = FakeLifecycle(
        state=FakeState("US.ABC", "BUY", 10, 10, 9, 12, "123", "PENDING"),
        status=type("Status", (), {"status": "SUBMITTING", "filled_quantity": 0, "average_price": 0})(),
    )

    result = _guarded_open(
        lifecycle, symbol="US.ABC", side="BUY", quantity=10, price=10, stop_price=9, target_price=12
    )

    assert result.action == "PENDING"
    assert result.broker_order_id == "123"
    assert "duplicate entry blocked" in result.reason
    assert lifecycle.notifications == []


def test_working_broker_order_is_reserved_when_state_is_missing():
    lifecycle = FakeLifecycle(
        broker_rows=[{"symbol": "US.ABC", "order_id": "456", "status": "SUBMITTING"}],
        status=type("Status", (), {"status": "SUBMITTING", "filled_quantity": 0, "average_price": 0})(),
    )

    result = _guarded_open(
        lifecycle, symbol="US.ABC", side="BUY", quantity=10, price=10, stop_price=9, target_price=12
    )

    assert result.action == "PENDING"
    assert result.broker_order_id == "456"
    assert lifecycle._state.state.status == "PENDING"
    assert lifecycle._state.state.broker_order_id == "456"
    assert any("ENTRY ALREADY WORKING" in message for message in lifecycle.notifications)
