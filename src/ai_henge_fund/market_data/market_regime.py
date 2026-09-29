"""Market-regime classification for the paper strategy gate.

This module uses only broad-index candle/quote evidence supplied by the
Moomoo scanner. It is deliberately deterministic: the AI may explain a
regime, but it does not get to override the safety classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class MarketRegime:
    label: str
    score: int
    spy_return_pct: float | None
    qqq_return_pct: float | None
    breadth_proxy: float | None
    reasons: tuple[str, ...]


def _closes(candles: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]) -> list[float]:
    values: list[float] = []
    for candle in candles:
        try:
            value = float(candle.get("close"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return values


def _return_pct(candles: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]], lookback: int = 4) -> float | None:
    closes = _closes(candles)
    if len(closes) <= lookback:
        return None
    base = closes[-1 - lookback]
    return ((closes[-1] / base) - 1.0) * 100.0 if base else None


def classify_market_regime(
    spy_candles: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    qqq_candles: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> MarketRegime:
    """Classify broad tape as RISK_ON, NEUTRAL, or RISK_OFF.

    The thresholds are intentionally modest. A regime label is a trade filter,
    not a prediction of the next market move.
    """
    spy_ret = _return_pct(spy_candles)
    qqq_ret = _return_pct(qqq_candles)
    valid = [value for value in (spy_ret, qqq_ret) if value is not None]
    if not valid:
        return MarketRegime("UNKNOWN", 0, spy_ret, qqq_ret, None, ("Broad-index data unavailable",))

    average = sum(valid) / len(valid)
    score = 0
    if average >= 0.25:
        score += 1
    elif average <= -0.25:
        score -= 1

    if spy_ret is not None:
        score += 1 if spy_ret >= 0.20 else -1 if spy_ret <= -0.20 else 0
    if qqq_ret is not None:
        score += 1 if qqq_ret >= 0.20 else -1 if qqq_ret <= -0.20 else 0

    if score >= 2:
        label = "RISK_ON"
    elif score <= -2:
        label = "RISK_OFF"
    else:
        label = "NEUTRAL"

    breadth_proxy = average
    reasons = (
        f"SPY 4-bar return={spy_ret:.2f}%" if spy_ret is not None else "SPY 4-bar return=NA",
        f"QQQ 4-bar return={qqq_ret:.2f}%" if qqq_ret is not None else "QQQ 4-bar return=NA",
        f"broad average={average:.2f}%",
    )
    return MarketRegime(label, score, spy_ret, qqq_ret, breadth_proxy, reasons)
