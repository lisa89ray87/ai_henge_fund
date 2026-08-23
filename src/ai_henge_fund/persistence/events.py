from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class TradeEvent:
    event_type: str
    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    occurred_at: datetime
    metadata: dict[str, Any]


class TradeEventStore(Protocol):
    def save(self, event: TradeEvent) -> None: ...


class InMemoryTradeEventStore:
    """Deterministic persistence seam used until Neon is wired in."""

    def __init__(self) -> None:
        self.events: list[TradeEvent] = []

    def save(self, event: TradeEvent) -> None:
        self.events.append(event)

    def all(self) -> list[TradeEvent]:
        return list(self.events)

    @staticmethod
    def serialize(event: TradeEvent) -> dict[str, Any]:
        payload = asdict(event)
        payload["occurred_at"] = event.occurred_at.isoformat()
        return payload
