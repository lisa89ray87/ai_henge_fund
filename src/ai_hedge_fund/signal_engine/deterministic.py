from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Any

from ai_hedge_fund.market_data.signal_snapshot import SignalSnapshot


@dataclass(frozen=True)
class DeterministicSignal:
    symbol: str
    direction: str
    score: int
    trend: int
    momentum: int
    price_action: int
    volume_confirmation: int
    market_alignment: int
    risk_reward: float | None
    setup_state: str
    reasons: tuple[str, ...]


class DeterministicSignalEngine:
    """Small, explainable first-pass signal engine.

    This intentionally mirrors the useful live-alert concepts without copying the
    provider-specific implementation. It is a gate before any LLM reasoning.
    """

    def evaluate(self, snapshot: SignalSnapshot) -> DeterministicSignal:
        if not snapshot.is_usable or len(snapshot.candles) < 2:
            return DeterministicSignal(
                symbol=snapshot.symbol,
                direction="NEUTRAL",
                score=0,
                trend=0,
                momentum=0,
                price_action=0,
                volume_confirmation=0,
                market_alignment=0,
                risk_reward=None,
                setup_state="DATA_INSUFFICIENT",
                reasons=("Insufficient usable market data",),
            )

        closes = [float(c["close"]) for c in snapshot.candles if c.get("close") is not None]
        if len(closes) < 2:
            return DeterministicSignal(
                symbol=snapshot.symbol, direction="NEUTRAL", score=0, trend=0,
                momentum=0, price_action=0, volume_confirmation=0,
                market_alignment=0, risk_reward=None,
                setup_state="DATA_INSUFFICIENT", reasons=("Candle close data unavailable",),
            )

        trend = 3 if closes[-1] > closes[0] else -3 if closes[-1] < closes[0] else 0
        momentum = 2 if closes[-1] > closes[-2] else -2 if closes[-1] < closes[-2] else 0
        price_action = 1 if closes[-1] > closes[0] else -1 if closes[-1] < closes[0] else 0
        volume_confirmation = 1 if snapshot.volume and snapshot.volume > 0 else 0
        market_alignment = 1 if snapshot.market_state and "END" not in snapshot.market_state else 0
        score = trend + momentum + price_action + volume_confirmation + market_alignment

        direction = "LONG" if score >= 4 else "SHORT" if score <= -4 else "NEUTRAL"
        setup_state = "CANDIDATE" if direction != "NEUTRAL" else "WAIT"
        reasons = [f"Trend={trend}", f"Momentum={momentum}", f"PriceAction={price_action}"]
        if volume_confirmation:
            reasons.append("Volume available")
        else:
            reasons.append("Volume confirmation unavailable")

        return DeterministicSignal(
            symbol=snapshot.symbol,
            direction=direction,
            score=score,
            trend=trend,
            momentum=momentum,
            price_action=price_action,
            volume_confirmation=volume_confirmation,
            market_alignment=market_alignment,
            risk_reward=None,
            setup_state=setup_state,
            reasons=tuple(reasons),
        )
