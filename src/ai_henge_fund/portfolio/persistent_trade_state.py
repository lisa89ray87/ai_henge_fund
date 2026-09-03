"""Persistent paper-trade state and trade-instance journal."""

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


@dataclass(frozen=True)
class TradeJournalEntry:
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    broker_entry_order_id: str | None
    opened_at: datetime
    status: str
    exit_quantity: float | None
    exit_price: float | None
    exit_reason: str | None
    broker_exit_order_id: str | None
    closed_at: datetime | None
    realized_pnl: float | None


class PersistentTradeStateStore:
    """PostgreSQL store for current paper positions plus immutable trade instances."""

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
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS paper_trade_journal (
                    trade_id VARCHAR(255) PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(8) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    entry_price NUMERIC(20, 8) NOT NULL,
                    stop_price NUMERIC(20, 8),
                    target_price NUMERIC(20, 8),
                    broker_entry_order_id VARCHAR(255),
                    opened_at TIMESTAMPTZ NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    exit_quantity NUMERIC(20, 8),
                    exit_price NUMERIC(20, 8),
                    exit_reason VARCHAR(32),
                    broker_exit_order_id VARCHAR(255),
                    closed_at TIMESTAMPTZ,
                    realized_pnl NUMERIC(20, 8)
                )
            """))
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_paper_trade_journal_symbol_opened
                ON paper_trade_journal (symbol, opened_at)
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

    def record_open(self, *, trade_id: str, symbol: str, side: str, quantity: float,
                    entry_price: float, stop_price: float | None, target_price: float | None,
                    broker_entry_order_id: str | None, opened_at: datetime | None = None) -> None:
        with session_scope() as session:
            session.execute(text("""
                INSERT INTO paper_trade_journal
                    (trade_id, symbol, side, quantity, entry_price, stop_price, target_price,
                     broker_entry_order_id, opened_at, status)
                VALUES
                    (:trade_id, :symbol, :side, :quantity, :entry_price, :stop_price, :target_price,
                     :broker_entry_order_id, :opened_at, 'OPEN')
                ON CONFLICT (trade_id) DO NOTHING
            """), {
                "trade_id": trade_id, "symbol": symbol.strip().upper(), "side": side.upper(),
                "quantity": quantity, "entry_price": entry_price, "stop_price": stop_price,
                "target_price": target_price, "broker_entry_order_id": broker_entry_order_id,
                "opened_at": opened_at or datetime.now(timezone.utc),
            })

    def record_exit(self, *, trade_id: str, quantity: float, exit_price: float,
                    exit_reason: str, broker_exit_order_id: str | None,
                    closed_at: datetime | None = None) -> None:
        now = closed_at or datetime.now(timezone.utc)
        with session_scope() as session:
            session.execute(text("""
                UPDATE paper_trade_journal
                SET exit_quantity = :quantity,
                    exit_price = :exit_price,
                    exit_reason = :exit_reason,
                    broker_exit_order_id = :broker_exit_order_id,
                    closed_at = :closed_at,
                    realized_pnl = CASE
                        WHEN side = 'BUY' THEN (:exit_price - entry_price) * :quantity
                        ELSE (entry_price - :exit_price) * :quantity
                    END,
                    status = CASE WHEN :quantity >= quantity THEN 'CLOSED' ELSE 'PARTIAL' END
                WHERE trade_id = :trade_id
            """), {
                "trade_id": trade_id, "quantity": quantity, "exit_price": exit_price,
                "exit_reason": exit_reason.upper(), "broker_exit_order_id": broker_exit_order_id,
                "closed_at": now,
            })

    def get_journal(self, trade_id: str) -> TradeJournalEntry | None:
        with session_scope() as session:
            row = session.execute(text("""
                SELECT trade_id, symbol, side, quantity, entry_price, stop_price, target_price,
                       broker_entry_order_id, opened_at, status, exit_quantity, exit_price,
                       exit_reason, broker_exit_order_id, closed_at, realized_pnl
                FROM paper_trade_journal WHERE trade_id = :trade_id
            """), {"trade_id": trade_id}).mappings().first()
        return self._journal(row) if row is not None else None

    def journal_for_day(self, day_start: datetime, day_end: datetime) -> list[TradeJournalEntry]:
        with session_scope() as session:
            rows = session.execute(text("""
                SELECT trade_id, symbol, side, quantity, entry_price, stop_price, target_price,
                       broker_entry_order_id, opened_at, status, exit_quantity, exit_price,
                       exit_reason, broker_exit_order_id, closed_at, realized_pnl
                FROM paper_trade_journal
                WHERE (opened_at >= :day_start AND opened_at < :day_end)
                   OR (closed_at >= :day_start AND closed_at < :day_end)
                ORDER BY COALESCE(closed_at, opened_at), symbol, opened_at
            """), {"day_start": day_start, "day_end": day_end}).mappings().all()
        return [self._journal(row) for row in rows]

    def open_journal(self) -> list[TradeJournalEntry]:
        with session_scope() as session:
            rows = session.execute(text("""
                SELECT trade_id, symbol, side, quantity, entry_price, stop_price, target_price,
                       broker_entry_order_id, opened_at, status, exit_quantity, exit_price,
                       exit_reason, broker_exit_order_id, closed_at, realized_pnl
                FROM paper_trade_journal
                WHERE status IN ('OPEN', 'PARTIAL')
                ORDER BY symbol, opened_at
            """)).mappings().all()
        return [self._journal(row) for row in rows]

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

    @staticmethod
    def _journal(row) -> TradeJournalEntry:
        return TradeJournalEntry(
            trade_id=row["trade_id"], symbol=row["symbol"], side=row["side"], quantity=float(row["quantity"]),
            entry_price=float(row["entry_price"]),
            stop_price=float(row["stop_price"]) if row["stop_price"] is not None else None,
            target_price=float(row["target_price"]) if row["target_price"] is not None else None,
            broker_entry_order_id=row["broker_entry_order_id"], opened_at=row["opened_at"],
            status=row["status"],
            exit_quantity=float(row["exit_quantity"]) if row["exit_quantity"] is not None else None,
            exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
            exit_reason=row["exit_reason"], broker_exit_order_id=row["broker_exit_order_id"],
            closed_at=row["closed_at"], realized_pnl=float(row["realized_pnl"]) if row["realized_pnl"] is not None else None,
        )
