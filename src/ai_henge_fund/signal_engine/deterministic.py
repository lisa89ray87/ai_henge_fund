from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot


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
    technical_context: dict[str, Any] | None = None


class DeterministicSignalEngine:
    """Explainable local technical pre-filter before any LLM call.

    The engine intentionally uses only the Moomoo candle/quote snapshot. It
    computes lightweight trend, momentum, volatility, price-location and volume
    features locally so the LLM is reserved for a small set of stronger setups.
    """

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values)

    @staticmethod
    def _rsi(closes: list[float], period: int = 14) -> float | None:
        if len(closes) <= period:
            return None
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent = changes[-period:]
        gains = [max(change, 0.0) for change in recent]
        losses = [max(-change, 0.0) for change in recent]
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

    @staticmethod
    def _atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
        ranges: list[float] = []
        for candle in candles[-period:]:
            try:
                high = float(candle["high"])
                low = float(candle["low"])
                ranges.append(max(0.0, high - low))
            except (KeyError, TypeError, ValueError):
                continue
        return sum(ranges) / len(ranges) if ranges else None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def evaluate(self, snapshot: SignalSnapshot) -> DeterministicSignal:
        if not snapshot.is_usable or len(snapshot.candles) < 15:
            return DeterministicSignal(
                symbol=snapshot.symbol, direction="NEUTRAL", score=0,
                trend=0, momentum=0, price_action=0, volume_confirmation=0,
                market_alignment=0, risk_reward=None,
                setup_state="DATA_INSUFFICIENT",
                reasons=("At least 15 usable candles are required for local technical filtering",),
            )

        candles = [dict(c) for c in snapshot.candles if c.get("close") is not None]
        closes = [self._safe_float(c.get("close")) for c in candles]
        closes = [value for value in closes if value is not None and value > 0]
        if len(closes) < 15:
            return DeterministicSignal(
                symbol=snapshot.symbol, direction="NEUTRAL", score=0,
                trend=0, momentum=0, price_action=0, volume_confirmation=0,
                market_alignment=0, risk_reward=None,
                setup_state="DATA_INSUFFICIENT",
                reasons=("Candle close data is insufficient for technical filtering",),
            )

        recent = closes[-20:]
        last = closes[-1]
        sma20 = self._mean(recent)
        first = closes[-15]
        slope_pct = ((last / first) - 1.0) * 100 if first else 0.0
        short_return_pct = ((last / closes[-4]) - 1.0) * 100 if len(closes) >= 4 else 0.0
        rsi = self._rsi(closes)
        atr = self._atr(candles)
        atr_pct = (atr / last * 100) if atr is not None and last else None

        highs = [self._safe_float(c.get("high")) for c in candles[-20:]]
        lows = [self._safe_float(c.get("low")) for c in candles[-20:]]
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        range_high = max(highs) if highs else last
        range_low = min(lows) if lows else last
        range_width = range_high - range_low
        range_position = ((last - range_low) / range_width) if range_width > 0 else 0.5

        volumes: list[float] = []
        for candle in candles[-20:]:
            value = self._safe_float(candle.get("volume"))
            if value is not None and value > 0:
                volumes.append(value)
        current_volume = self._safe_float(snapshot.volume)
        avg_volume = self._mean(volumes[:-1]) if len(volumes) > 1 else None
        volume_ratio = (current_volume / avg_volume) if current_volume and avg_volume else None

        # Directional components: trend +/-3, momentum +/-2, price action +/-2,
        # volume +/-1, market alignment +/-1. Strong setups therefore require
        # agreement from multiple independent local features.
        trend = 0
        if last > sma20 and slope_pct >= 0.4:
            trend = 3
        elif last < sma20 and slope_pct <= -0.4:
            trend = -3
        elif last > sma20:
            trend = 1
        elif last < sma20:
            trend = -1

        momentum = 0
        if rsi is not None:
            if 52 <= rsi <= 68 and short_return_pct > 0:
                momentum = 2
            elif 32 <= rsi <= 48 and short_return_pct < 0:
                momentum = -2
            elif rsi > 50 and short_return_pct > 0:
                momentum = 1
            elif rsi < 50 and short_return_pct < 0:
                momentum = -1
        elif short_return_pct > 0:
            momentum = 1
        elif short_return_pct < 0:
            momentum = -1

        price_action = 0
        last_candle = candles[-1]
        candle_open = self._safe_float(last_candle.get("open"))
        candle_high = self._safe_float(last_candle.get("high"))
        candle_low = self._safe_float(last_candle.get("low"))
        if candle_open is not None and candle_high is not None and candle_low is not None:
            candle_range = candle_high - candle_low
            if candle_range > 0:
                close_location = (last - candle_low) / candle_range
                if last > candle_open and close_location >= 0.65:
                    price_action = 2
                elif last < candle_open and close_location <= 0.35:
                    price_action = -2
        if price_action == 0:
            if range_position >= 0.65 and last >= sma20:
                price_action = 1
            elif range_position <= 0.35 and last <= sma20:
                price_action = -1

        volume_confirmation = 0
        if volume_ratio is not None:
            if volume_ratio >= 1.10 and ((trend > 0 and momentum >= 0) or (trend < 0 and momentum <= 0)):
                volume_confirmation = 1 if trend > 0 else -1
            elif volume_ratio >= 0.80:
                volume_confirmation = 0

        market_alignment = 0
        market_state = (snapshot.market_state or "").upper()
        if market_state and "END" not in market_state:
            market_alignment = 1

        score = trend + momentum + price_action + volume_confirmation + market_alignment
        direction = "LONG" if score >= 5 else "SHORT" if score <= -5 else "NEUTRAL"
        setup_state = "CANDIDATE" if direction != "NEUTRAL" else "WAIT"

        reasons = [
            f"Trend={trend} SMA20={sma20:.2f} slope15={slope_pct:.2f}%",
            f"Momentum={momentum} RSI14={rsi:.1f}" if rsi is not None else f"Momentum={momentum} RSI14=NA",
            f"PriceAction={price_action} range_position={range_position:.2f}",
            f"VolConfirm={volume_confirmation} volume_ratio={volume_ratio:.2f}" if volume_ratio is not None else f"VolConfirm={volume_confirmation} volume_ratio=NA",
        ]
        if atr_pct is not None:
            reasons.append(f"ATR14={atr:.4f} ({atr_pct:.2f}%)")
        if market_state:
            reasons.append(f"Market={market_state}")

        technical_context = {
            "sma20": round(sma20, 4),
            "slope15_pct": round(slope_pct, 4),
            "short_return_pct": round(short_return_pct, 4),
            "rsi14": round(rsi, 4) if rsi is not None else None,
            "atr14": round(atr, 6) if atr is not None else None,
            "atr_pct": round(atr_pct, 4) if atr_pct is not None else None,
            "range_position_20": round(range_position, 4),
            "volume_ratio": round(volume_ratio, 4) if volume_ratio is not None else None,
        }

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
            technical_context=technical_context,
        )
