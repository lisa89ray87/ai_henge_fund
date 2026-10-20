"""Offline regression tests for the Gemini -> secondary AI fallback path."""
import os
from unittest.mock import patch

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime, TradingAgentsDecision


def _runtime():
    runtime = object.__new__(TradingAgentsGraphRuntime)
    runtime._cancelled_symbols = set()
    import threading
    runtime._cancel_lock = threading.Lock()
    return runtime


def test_gemini_outage_calls_secondary():
    runtime = _runtime()
    expected = TradingAgentsDecision("SELL", 0.8, "test", "third-party-responses", 1, 100, 102, 96)
    with patch.dict(os.environ, {"TRADINGAGENTS_LIGHTWEIGHT_PAPER_AI": "true", "THIRD_PARTY_API_KEY": "placeholder"}):
        with patch.object(runtime, "_run_lightweight_gemini", side_effect=RuntimeError("503 UNAVAILABLE")):
            with patch.object(runtime, "_run_third_party", return_value=expected) as secondary:
                result = runtime.analyze({"symbol": "US.TSLA"})
    assert result is expected
    secondary.assert_called_once()


def test_both_providers_fail_closed():
    runtime = _runtime()
    with patch.dict(os.environ, {"TRADINGAGENTS_LIGHTWEIGHT_PAPER_AI": "true", "THIRD_PARTY_API_KEY": "placeholder"}):
        with patch.object(runtime, "_run_lightweight_gemini", side_effect=RuntimeError("503 UNAVAILABLE")):
            with patch.object(runtime, "_run_third_party", side_effect=RuntimeError("secondary unavailable")):
                result = runtime.analyze({"symbol": "US.TSLA"})
    assert result.action == "WAIT"
    assert result.quantity is None


def test_valid_gemini_wait_never_calls_secondary():
    runtime = _runtime()
    expected = TradingAgentsDecision("WAIT", 0.4, "no setup", "google_genai-lightweight")
    with patch.dict(os.environ, {"TRADINGAGENTS_LIGHTWEIGHT_PAPER_AI": "true", "THIRD_PARTY_API_KEY": "placeholder"}):
        with patch.object(runtime, "_run_lightweight_gemini", return_value=expected):
            with patch.object(runtime, "_run_third_party") as secondary:
                result = runtime.analyze({"symbol": "US.TSLA"})
    assert result is expected
    secondary.assert_not_called()
