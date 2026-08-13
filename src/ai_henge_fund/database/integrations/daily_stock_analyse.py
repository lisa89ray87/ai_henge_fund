"""Read-only bridge from the existing daily_stock_analyse signal engine.

The existing repository remains the source of truth for its live alerts,
catalysts, market-regime analysis, and signal lifecycle. This adapter reads
those persisted signals and normalizes them into AI Henge Fund's own signal
namespace without modifying the source tables.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_henge_fund.database.models.signal import Signal, SignalAction
from ai_henge_fund.database.models.strategy import Strategy

DAILY_STOCK_ANALYSE_SOURCE = "daily_stock_analyse"
DAILY_STOCK_ANALYSE_STRATEGY = "daily_stock_analyse"

_DAILY_SIGNAL_QUERY = text(
    """
    SELECT
        signal_id,
        run_id,
        symbol,
        direction,
        status,
        confidence,
        target_1,
        catalyst,
        catalyst_status,
        catalyst_category,
        catalyst_direction,
        market_regime_label,
        created_at,
        updated_at
    FROM signals
    WHERE direction IN ('LONG', 'SHORT')
      AND (:since IS NULL OR created_at >= :since)
    ORDER BY created_at ASC
    LIMIT :limit
    """
)


def _confidence_value(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    mapping = {"HIGH": Decimal("0.90"), "MEDIUM": Decimal("0.60"), "LOW": Decimal("0.30")}
    return mapping.get(str(value).strip().upper())


def _action(direction: str) -> SignalAction:
    normalized = direction.strip().upper()
    if normalized == "LONG":
        return SignalAction.BUY
    if normalized == "SHORT":
        return SignalAction.SELL
    raise ValueError(f"Unsupported daily_stock_analyse direction: {direction}")


def _reasoning(row: dict[str, Any]) -> str:
    parts = [
        "Imported from daily_stock_analyse",
        f"status={row.get('status') or 'UNKNOWN'}",
        f"market_regime={row.get('market_regime_label') or 'UNKNOWN'}",
    ]
    if row.get("catalyst_status"):
        parts.append(f"catalyst_status={row['catalyst_status']}")
    if row.get("catalyst_category"):
        parts.append(f"catalyst_category={row['catalyst_category']}")
    if row.get("catalyst_direction"):
        parts.append(f"catalyst_direction={row['catalyst_direction']}")
    if row.get("catalyst"):
        parts.append(f"catalyst={row['catalyst']}")
    if row.get("run_id"):
        parts.append(f"run_id={row['run_id']}")
    return "; ".join(parts)


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    return dict(row._mapping)


def _get_or_create_strategy(session: Session) -> Strategy:
    strategy = session.query(Strategy).filter_by(name=DAILY_STOCK_ANALYSE_STRATEGY).one_or_none()
    if strategy is None:
        strategy = Strategy(
            name=DAILY_STOCK_ANALYSE_STRATEGY,
            description="Imported signals from the existing daily_stock_analyse engine.",
            version="1",
            enabled=True,
        )
        session.add(strategy)
        session.flush()
    return strategy


def sync_daily_stock_signals(
    session: Session,
    *,
    since: datetime | None = None,
    limit: int = 500,
) -> int:
    """Import new daily_stock_analyse signals without changing source tables.

    Returns the number of AI Henge Fund rows inserted. Existing source IDs are
    deduplicated through the ``(source, source_signal_id)`` unique constraint.
    """
    if limit < 1 or limit > 5000:
        raise ValueError("limit must be between 1 and 5000")

    strategy = _get_or_create_strategy(session)
    result = session.execute(_DAILY_SIGNAL_QUERY, {"since": since, "limit": limit})
    inserted = 0

    for raw_row in result.mappings():
        row = _as_dict(raw_row)
        source_signal_id = str(row["signal_id"])
        existing = (
            session.query(Signal)
            .filter_by(source=DAILY_STOCK_ANALYSE_SOURCE, source_signal_id=source_signal_id)
            .one_or_none()
        )
        if existing is not None:
            continue

        generated_at = row.get("created_at") or row.get("updated_at")
        if generated_at is None:
            raise ValueError(f"daily_stock_analyse signal {source_signal_id} has no timestamp")

        session.add(
            Signal(
                strategy_id=strategy.id,
                symbol=str(row["symbol"]).upper(),
                action=_action(str(row["direction"])),
                confidence=_confidence_value(row.get("confidence")),
                target_price=row.get("target_1"),
                reasoning=_reasoning(row),
                source=DAILY_STOCK_ANALYSE_SOURCE,
                source_signal_id=source_signal_id,
                generated_at=generated_at,
            )
        )
        inserted += 1

    return inserted
