from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_hedge_fund.trading.pipeline import TradingPipeline
from ai_hedge_fund.tradingagents.adapter import AITradeDecision, TradingAgentsAdapter


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
