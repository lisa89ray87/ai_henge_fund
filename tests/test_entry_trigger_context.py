import math

from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime


def _candles(last_close=105.0):
    rows = []
    for i in range(20):
        close = 100.0 + i * 0.1
        rows.append({"open": close - 0.2, "high": close + 0.3,
                     "low": close - 0.3, "close": close, "volume": 1000})
    rows[-1] = {"open": 103.0, "high": last_close + 0.2,
                "low": 102.9, "close": last_close, "volume": 1500}
    return rows


def test_long_breakout_has_structured_evidence():
    context = DeterministicSignalEngine._entry_trigger_context(_candles(), "LONG")
    assert context["status"] == "AVAILABLE"
    assert context["trigger"] == "BREAKOUT"
    assert context["breakout"] is True
    assert context["vwap"] is not None
    assert context["session_rvol"] is None


def test_missing_candles_do_not_invent_trigger():
    context = DeterministicSignalEngine._entry_trigger_context([], "SHORT")
    assert context["status"] == "UNAVAILABLE"
    assert context["trigger"] == "NONE"
    assert context["opening_range"] == "UNAVAILABLE"


def test_ai_prompt_explains_trigger_and_volume_limitations():
    runtime = TradingAgentsGraphRuntime.__new__(TradingAgentsGraphRuntime)
    prompt = runtime._build_lightweight_prompt({
        "symbol": "US.AAPL", "market": {"candles": _candles()},
        "deterministic_signal": {"technical_context": {
            "entry_trigger": {"trigger": "BREAKOUT", "session_rvol": None}}},
    })
    assert "session-aware RVOL" in prompt
    assert "EMA9 retest" in prompt
    assert '"trigger":"BREAKOUT"' in prompt


def test_nan_ohlc_rejected():
    candles = _candles()
    candles[-1]["low"] = math.nan
    context = DeterministicSignalEngine._entry_trigger_context(candles, "LONG")
    assert context["status"] == "UNAVAILABLE"
    assert context["trigger"] == "NONE"


def test_zero_volume_candle_still_allows_vwap():
    candles = _candles()
    candles[3]["volume"] = 0
    context = DeterministicSignalEngine._entry_trigger_context(candles, "LONG")
    assert context["vwap"] is not None


def test_no_false_long_retest_from_updated_ema():
    candles = [{"open": 100, "high": 100.2, "low": 99.8, "close": 100, "volume": 100}
               for _ in range(19)]
    candles.append({"open": 100.1, "high": 101.1, "low": 100.1, "close": 101, "volume": 100})
    context = DeterministicSignalEngine._entry_trigger_context(candles, "LONG")
    assert context["ema_retest"] is False


def test_no_false_short_retest_from_updated_ema():
    candles = [{"open": 100, "high": 100.2, "low": 99.8, "close": 100, "volume": 100}
               for _ in range(19)]
    candles.append({"open": 99.9, "high": 99.9, "low": 98.9, "close": 99, "volume": 100})
    context = DeterministicSignalEngine._entry_trigger_context(candles, "SHORT")
    assert context["ema_retest"] is False
