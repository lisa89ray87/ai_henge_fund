from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from scripts.send_paper_extended_hours_stop_reminder import _build_message, _current_window


ET = ZoneInfo("America/New_York")


def test_pre_market_reminder_window() -> None:
    now = datetime(2026, 9, 4, 3, 55, tzinfo=ET)
    assert _current_window(now) == "PRE-MARKET"


def test_post_market_prep_window() -> None:
    now = datetime(2026, 9, 4, 15, 55, tzinfo=ET)
    assert _current_window(now) == "POST-MARKET PREP"


def test_non_trigger_time_is_noop() -> None:
    now = datetime(2026, 9, 4, 15, 54, tzinfo=ET)
    assert _current_window(now) is None


def test_message_is_paper_only_and_explicit_about_overnight_limit() -> None:
    state = SimpleNamespace(
        symbol="US.AAPL",
        side="BUY",
        quantity=2.0,
        entry_price=200.0,
        stop_price=195.0,
        target_price=210.0,
    )
    message = _build_message("POST-MARKET PREP", [state])
    assert "PAPER EXTENDED-HOURS PROTECTION" in message
    assert "US.AAPL LONG" in message
    assert "Manual protection side: SELL" in message
    assert "does not support US-stock pre-market, after-hours, or overnight order execution" in message
    assert "live trading is unaffected" in message
