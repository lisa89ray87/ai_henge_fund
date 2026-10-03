from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class PremarketSymbolContext:
    symbol: str
    previous_close: float | None
    premarket_price: float | None
    premarket_change_pct: float | None
    premarket_volume: int | None
    premarket_high: float | None
    premarket_low: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "previous_close": self.previous_close,
            "premarket_price": self.premarket_price,
            "premarket_change_pct": self.premarket_change_pct,
            "premarket_volume": self.premarket_volume,
            "premarket_high": self.premarket_high,
            "premarket_low": self.premarket_low,
        }


@dataclass(frozen=True)
class PremarketContext:
    generated_at: datetime
    market_bias: str
    market_confidence: float
    market_risk: str
    spy: Mapping[str, Any]
    qqq: Mapping[str, Any]
    notable_symbols: tuple[PremarketSymbolContext, ...]
    ai_rationale: str
    ai_provider: str

    def for_symbol(self, symbol: str) -> dict[str, Any]:
        normalized = symbol.strip().upper()
        match = next((item for item in self.notable_symbols if item.symbol == normalized), None)
        return {
            "generated_at": self.generated_at.isoformat(),
            "market_bias": self.market_bias,
            "market_confidence": self.market_confidence,
            "market_risk": self.market_risk,
            "spy": dict(self.spy),
            "qqq": dict(self.qqq),
            "symbol": match.to_dict() if match else {"symbol": normalized},
            "notable_symbols": [item.to_dict() for item in self.notable_symbols],
            "ai_rationale": self.ai_rationale,
            "ai_provider": self.ai_provider,
        }


def extract_premarket(quote: Any) -> PremarketSymbolContext:
    raw = dict(getattr(quote, "raw", None) or {})
    symbol = str(getattr(quote, "symbol", raw.get("code", ""))).upper()
    previous_close = getattr(quote, "previous_close", None)
    pre_price = raw.get("pre_price")
    pre_change = raw.get("pre_change_rate")
    pre_volume = raw.get("pre_volume")
    pre_high = raw.get("pre_high_price")
    pre_low = raw.get("pre_low_price")
    return PremarketSymbolContext(
        symbol=symbol,
        previous_close=float(previous_close) if previous_close is not None else None,
        premarket_price=float(pre_price) if pre_price is not None else None,
        premarket_change_pct=float(pre_change) if pre_change is not None else None,
        premarket_volume=int(pre_volume) if pre_volume is not None else None,
        premarket_high=float(pre_high) if pre_high is not None else None,
        premarket_low=float(pre_low) if pre_low is not None else None,
    )


def summarize_quote(quote: Any) -> dict[str, Any]:
    item = extract_premarket(quote)
    return {
        "symbol": item.symbol,
        "previous_close": item.previous_close,
        "premarket_price": item.premarket_price,
        "premarket_change_pct": item.premarket_change_pct,
        "premarket_volume": item.premarket_volume,
    }


def build_premarket_candidates(quotes: list[Any], *, limit: int = 12) -> list[PremarketSymbolContext]:
    contexts = [extract_premarket(quote) for quote in quotes]
    contexts = [
        item for item in contexts
        if item.premarket_price is not None and item.premarket_change_pct is not None
    ]
    contexts.sort(
        key=lambda item: (
            abs(item.premarket_change_pct or 0.0),
            item.premarket_volume or 0,
        ),
        reverse=True,
    )
    return contexts[:max(1, limit)]
