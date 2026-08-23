from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.trading.pipeline import TradingPipeline
from ai_henge_fund.tradingagents.adapter import AITradeDecision, TradingAgentsAdapter

from dataclasses import dataclass
from ai_henge_fund.execution.moomoo_order_monitor import MoomooOrderStatus
from ai_henge_fund.execution.moomoo_paper import MoomooPaperOrder
from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooPaperTradeLifecycle
from ai_henge_fund.portfolio.manager import PositionManager


class Runner:
    def analyze(self, payload):
        assert payload["capabilities"]["orders"] is False
        return {"decision": "BUY", "confidence": 0.90, "rationale": "test confirmation"}


def test_pipeline_opens_paper_position_only_after_all_gates():
    snapshot = SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="REGULAR", candles=tuple({"close": x} for x in [100, 101, 103]),
        data_source="test", data_quality="LIVE",
    )
    pipeline = TradingPipeline(ai_adapter=TradingAgentsAdapter(Runner()))

    # Inject a lifecycle that simulates an immediate full fill for the
    # Moomoo paper order so the pipeline opens a position (OPEN).
    @dataclass
    class FakeExecution:
        order_id: str = "12345"

        def place_limit(self, *, symbol: str, side: str, quantity: int, price: float) -> MoomooPaperOrder:
            return MoomooPaperOrder(
                order_id=self.order_id,
                symbol=symbol,
                side=side,
                quantity=float(quantity),
                price=price,
                status="SUBMITTING",
                raw=None,
            )

        def close(self) -> None:
            pass

    @dataclass
    class FakeMonitor:
        result: MoomooOrderStatus

        def wait_for_terminal(self, order_id: str, timeout_seconds: int = 30) -> MoomooOrderStatus:
            return self.result

        def close(self) -> None:
            pass

    # Inject a fake lifecycle that immediately reports an OPEN trade with
    # a `PaperTrade` status of "FILLED" so the pipeline's assertions hold.
    from ai_henge_fund.paper_trading.engine import PaperTrade
    from datetime import datetime, timezone

    @dataclass
    class FakeLifecycle:
        def open(self, *, symbol: str, side: str, quantity: float, price: float):
            trade = PaperTrade(
                trade_id="paper-12345",
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                executed_at=datetime.now(timezone.utc),
            )
            return MoomooPaperTradeLifecycle.__annotations__["return"] if False else None

    # Build a MoomooLifecycleResult-like object to match pipeline expectations.
    # Instead of constructing via MoomooPaperTradeLifecycle (which uses FILLED_ALL),
    # create the result directly when `open` is called by the pipeline.
    class LifecycleProxy:
        def open(self, *, symbol: str, side: str, quantity: float, price: float):
            trade = PaperTrade(
                trade_id="paper-12345",
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                executed_at=datetime.now(timezone.utc),
            )
            # Mimic MoomooLifecycleResult structure
            from ai_henge_fund.paper_trading.moomoo_lifecycle import MoomooLifecycleResult

            return MoomooLifecycleResult("OPEN", trade, "Moomoo paper order fully filled", broker_order_id="12345", broker_status="FILLED")

    pipeline._lifecycle = LifecycleProxy()

    result = pipeline.evaluate(snapshot)

    assert result.risk.action == "BUY"
    assert result.lifecycle is not None
    assert result.lifecycle.action == "OPEN"
    assert result.lifecycle.trade.status == "FILLED"


def test_pipeline_does_not_open_when_ai_disagrees():
    class BearishRunner:
        def analyze(self, payload):
            return {"decision": "SELL", "confidence": 0.95, "rationale": "disagreement"}

    snapshot = SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="REGULAR", candles=tuple({"close": x} for x in [100, 101, 103]),
        data_source="test", data_quality="LIVE",
    )
    result = TradingPipeline(ai_adapter=TradingAgentsAdapter(BearishRunner())).evaluate(snapshot)
    assert result.risk.action == "WAIT"
    assert result.lifecycle is None
