from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.risk.gate import RiskGate
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.tradingagents.adapter import AITradeDecision


def make_snapshot():
    return SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="REGULAR", candles=tuple({"close": 100 + i * 0.3, "low": 99 + i * 0.3, "high": 101 + i * 0.3} for i in range(20)),
        data_source="test", data_quality="LIVE", metadata={"market_regime": "RISK_ON"},
    )


def make_long_candidate(snapshot, score=7):
    signal = DeterministicSignalEngine().evaluate(snapshot)
    return signal.__class__(
        symbol=signal.symbol, direction="LONG", score=score,
        trend=signal.trend, momentum=signal.momentum,
        price_action=signal.price_action, volume_confirmation=signal.volume_confirmation,
        market_alignment=signal.market_alignment, risk_reward=signal.risk_reward,
        setup_state="CANDIDATE", reasons=signal.reasons, technical_context=signal.technical_context,
    )


def test_risk_gate_accepts_confirmed_candidate():
    snapshot = make_snapshot()
    signal = make_long_candidate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.85, "confirmed", "test", quantity=1, entry_price=100, stop_price=99, target_price=102)
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "BUY"
    assert result.quantity == 1
    assert "AI_CONFIDENCE" in result.checks


def test_risk_gate_fails_on_low_ai_confidence():
    snapshot = make_snapshot()
    signal = make_long_candidate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.50, "weak", "test")
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "WAIT"
    assert result.quantity == 0


def test_risk_gate_rejects_closed_market_state():
    snapshot = SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="AFTER_HOURS_END", candles=tuple({"close": 100 + i * 0.3, "low": 99 + i * 0.3, "high": 101 + i * 0.3} for i in range(20)),
        data_source="test", data_quality="LIVE", metadata={"market_regime": "RISK_OFF"},
    )
    signal = make_long_candidate(snapshot)
    ai = AITradeDecision("US.AAPL", "BUY", 0.90, "confirmed", "test")
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "WAIT"


def test_risk_gate_allows_candidate_when_market_regime_is_unknown():
    snapshot = SignalSnapshot(
        symbol="US.AAPL", timestamp=None, last_price=100, volume=1000,
        market_state="REGULAR",
        candles=tuple({"close": 100 + i * 0.3, "low": 99 + i * 0.3, "high": 101 + i * 0.3} for i in range(20)),
        data_source="test", data_quality="LIVE", metadata={"market_regime": "UNKNOWN"},
    )
    signal = make_long_candidate(snapshot)
    ai = AITradeDecision(
        "US.AAPL", "BUY", 0.85, "confirmed", "test",
        quantity=1, entry_price=100, stop_price=99, target_price=102,
    )
    result = RiskGate().evaluate(snapshot, signal, ai)
    assert result.action == "BUY"
    assert "MARKET_REGIME_UNKNOWN" in result.checks
    assert "Broad-market regime is unavailable" not in result.reason



def test_aggressive_paper_profile_lowers_confidence_threshold(monkeypatch):
    monkeypatch.setenv("AI_HEDGE_FUND_RISK_PROFILE", "aggressive_paper")
    monkeypatch.setenv("MOOMOO_PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("MOOMOO_LIVE_TRADING_ENABLED", "false")
    from ai_henge_fund.config.settings import get_settings
    get_settings.cache_clear()
    try:
        gate = RiskGate()
        assert gate.min_ai_confidence == 0.70
        assert gate.risk_profile == "aggressive_paper"
    finally:
        get_settings.cache_clear()


def test_aggressive_paper_allows_strong_favorable_setup_at_1_75_rr(monkeypatch):
    monkeypatch.setenv("AI_HEDGE_FUND_RISK_PROFILE", "aggressive_paper")
    monkeypatch.setenv("MOOMOO_PAPER_TRADING_ENABLED", "true")
    monkeypatch.setenv("MOOMOO_LIVE_TRADING_ENABLED", "false")
    from ai_henge_fund.config.settings import get_settings
    get_settings.cache_clear()
    try:
        snapshot = make_snapshot()
        signal = make_long_candidate(snapshot, score=7)
        ai = AITradeDecision(
            "US.AAPL", "BUY", 0.72, "confirmed", "test",
            quantity=1, entry_price=100, stop_price=99.9, target_price=101.65,
        )
        result = RiskGate().evaluate(snapshot, signal, ai)
        assert result.action == "BUY"
        assert "RISK_PROFILE_AGGRESSIVE_PAPER" in result.checks
        assert "ADAPTIVE_REWARD_RISK_1_75" in result.checks
    finally:
        get_settings.cache_clear()
