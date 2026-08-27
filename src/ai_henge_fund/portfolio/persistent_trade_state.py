"""Persistent paper-trade state used to resume positions across workflow runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from ai_henge_fund.database.session import session_scope


@dataclass(frozen=True)
class TradeState:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    broker_order_id: str | None
    status: str
    updated_at: datetime


class PersistentTradeStateStore:
    """Idempotent PostgreSQL store for paper positions and protection levels."""

    def __init__(self) -> None:
        self._ensure_table()

    def _ensure_table(self) -> None:
        with session_scope() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS paper_trade_states (
                    symbol VARCHAR(32) PRIMARY KEY,
                    side VARCHAR(8) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    entry_price NUMERIC(20, 8) NOT NULL,
                    stop_price NUMERIC(20, 8),
                    target_price NUMERIC(20, 8),
                    broker_order_id VARCHAR(255),
                    status VARCHAR(32) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            """))

    def upsert(self, *, symbol: str, side: str, quantity: float, entry_price: float,
               stop_price: float | None, target_price: float | None,
               broker_order_id: str | None, status: str = "OPEN") -> None:
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            session.execute(text("""
                INSERT INTO paper_trade_states
                    (symbol, side, quantity, entry_price, stop_price, target_price,
                     broker_order_id, status, updated_at)
                VALUES
                    (:symbol, :side, :quantity, :entry_price, :stop_price, :target_price,
                     :broker_order_id, :status, :updated_at)
                ON CONFLICT (symbol) DO UPDATE SET
                    side = EXCLUDED.side,
                    quantity = EXCLUDED.quantity,
                    entry_price = EXCLUDED.entry_price,
                    stop_price = EXCLUDED.stop_price,
                    target_price = EXCLUDED.target_price,
                    broker_order_id = EXCLUDED.broker_order_id,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at
            """), {
                "symbol": symbol.strip().upper(), "side": side.upper(), "quantity": quantity,
                "entry_price": entry_price, "stop_price": stop_price, "target_price": target_price,
                "broker_order_id": broker_order_id, "status": status, "updated_at": now,
            })

    def get(self, symbol: str) -> TradeState | None:
        with session_scope() as session:
            row = session.execute(text("""
                SELECT symbol, side, quantity, entry_price, stop_price, target_price,
                       broker_order_id, status, updated_at
                FROM paper_trade_states WHERE symbol = :symbol
            """), {"symbol": symbol.strip().upper()}).mappings().first()
        if row is None:
            return None
        return self._state(row)

    def mark_closed(self, symbol: str) -> None:
        with session_scope() as session:
            session.execute(text("""
                UPDATE paper_trade_states
                SET status = 'CLOSED', updated_at = :updated_at
                WHERE symbol = :symbol
            """), {"symbol": symbol.strip().upper(), "updated_at": datetime.now(timezone.utc)})

    def open_states(self) -> list[TradeState]:
        with session_scope() as session:
            rows = session.execute(text("""
                SELECT symbol, side, quantity, entry_price, stop_price, target_price,
                       broker_order_id, status, updated_at
                FROM paper_trade_states WHERE status = 'OPEN'
                ORDER BY symbol
            """)).mappings().all()
        return [self._state(row) for row in rows]

    @staticmethod
    def _state(row) -> TradeState:
        return TradeState(
            symbol=row["symbol"], side=row["side"], quantity=float(row["quantity"]),
            entry_price=float(row["entry_price"]),
            stop_price=float(row["stop_price"]) if row["stop_price"] is not None else None,
            target_price=float(row["target_price"]) if row["target_price"] is not None else None,
            broker_order_id=row["broker_order_id"], status=row["status"], updated_at=row["updated_at"],
        )
