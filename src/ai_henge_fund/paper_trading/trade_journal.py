from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from ai_henge_fund.database.session import session_scope


@dataclass(frozen=True)
class TradeExitEvent:
    exit_id: int
    trade_id: str
    quantity: float
    exit_price: float
    reason: str
    broker_exit_order_id: str | None
    exited_at: datetime
    realized_pnl: float


class TradeJournal:
    """Append-only exit-event journal for paper trade instances."""

    def __init__(self) -> None:
        with session_scope() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS paper_trade_exit_events (
                    exit_id BIGSERIAL PRIMARY KEY,
                    trade_id VARCHAR(255) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    exit_price NUMERIC(20, 8) NOT NULL,
                    reason VARCHAR(32) NOT NULL,
                    broker_exit_order_id VARCHAR(255),
                    exited_at TIMESTAMPTZ NOT NULL,
                    realized_pnl NUMERIC(20, 8) NOT NULL
                )
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_paper_trade_exit_events_trade
                ON paper_trade_exit_events (trade_id, exited_at)
            """))

    def record_exit(self, *, trade_id: str, entry_side: str, entry_price: float,
                    quantity: float, exit_price: float, reason: str,
                    broker_exit_order_id: str | None,
                    exited_at: datetime | None = None) -> TradeExitEvent:
        if quantity <= 0 or exit_price <= 0:
            raise ValueError("exit quantity and price must be positive")
        side = entry_side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("entry_side must be BUY or SELL")
        pnl = ((exit_price - entry_price) if side == "BUY" else (entry_price - exit_price)) * quantity
        when = exited_at or datetime.now(timezone.utc)
        with session_scope() as session:
            exit_id = session.execute(text("""
                INSERT INTO paper_trade_exit_events
                    (trade_id, quantity, exit_price, reason, broker_exit_order_id, exited_at, realized_pnl)
                VALUES
                    (:trade_id, :quantity, :exit_price, :reason, :broker_exit_order_id, :exited_at, :realized_pnl)
                RETURNING exit_id
            """), {
                "trade_id": trade_id,
                "quantity": quantity,
                "exit_price": exit_price,
                "reason": reason.upper(),
                "broker_exit_order_id": broker_exit_order_id,
                "exited_at": when,
                "realized_pnl": pnl,
            }).scalar_one()
        return TradeExitEvent(
            int(exit_id), trade_id, quantity, exit_price, reason.upper(),
            broker_exit_order_id, when, pnl,
        )

    def exits_for_trade(self, trade_id: str) -> list[TradeExitEvent]:
        with session_scope() as session:
            rows = session.execute(text("""
                SELECT exit_id, trade_id, quantity, exit_price, reason,
                       broker_exit_order_id, exited_at, realized_pnl
                FROM paper_trade_exit_events
                WHERE trade_id = :trade_id
                ORDER BY exited_at, exit_id
            """), {"trade_id": trade_id}).mappings().all()
        return [TradeExitEvent(
            int(row["exit_id"]), row["trade_id"], float(row["quantity"]),
            float(row["exit_price"]), row["reason"], row["broker_exit_order_id"],
            row["exited_at"], float(row["realized_pnl"]),
        ) for row in rows]
