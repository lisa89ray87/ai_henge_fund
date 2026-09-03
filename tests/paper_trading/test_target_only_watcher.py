from dataclasses import dataclass

from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooPaperTradeLifecycle


@dataclass
class FakeOrder:
    order_id: str = "entry-1"
    status: str = "SUBMITTED"


@dataclass
class FakeStatus:
    status: str = "FILLED_ALL"
    filled_quantity: float = 1.0
    average_price: float = 10.0


class FakeExecution:
    def place_limit(self, **kwargs):
        return FakeOrder()


class FakeMonitor:
    def wait_for_terminal(self, order_id, timeout_seconds):
        return FakeStatus()


class FakePositions:
    def __init__(self):
        self.position = None

    def get(self, symbol):
        return self.position

    def open_signed(self, symbol, quantity, price, *, stop_price=None, target_price=None):
        self.position = object()


class FakeState:
    def upsert(self, **kwargs):
        pass

    def record_open(self, **kwargs):
        pass


class FakeJournal:
    pass


def test_open_starts_watcher_when_target_exists_without_local_stop():
    lifecycle = MoomooPaperTradeLifecycle.__new__(MoomooPaperTradeLifecycle)
    lifecycle.execution = FakeExecution()
    lifecycle.monitor = FakeMonitor()
    lifecycle.positions = FakePositions()
    lifecycle.telegram = None
    lifecycle.fill_timeout_seconds = 30
    lifecycle._state = FakeState()
    lifecycle._trade_journal = FakeJournal()
    lifecycle._target_orders = {}
    lifecycle._watchers = {}

    armed = []
    started = []
    lifecycle._arm_target = lambda symbol, side, quantity, target_price, *, notify: armed.append(
        (symbol, side, quantity, target_price)
    ) or "target-1"
    lifecycle._start_exit_watcher = lambda symbol, side, quantity, stop_price, target_order_id: started.append(
        (symbol, side, quantity, stop_price, target_order_id)
    )
    lifecycle._notify = lambda *args, **kwargs: None

    result = lifecycle.open(
        symbol="US.TEST",
        side="BUY",
        quantity=1,
        price=10.0,
        stop_price=None,
        target_price=12.0,
    )

    assert result.action == "OPEN"
    assert armed == [("US.TEST", "BUY", 1, 12.0)]
    assert started == [("US.TEST", "BUY", 1, 0.0, "target-1")]
