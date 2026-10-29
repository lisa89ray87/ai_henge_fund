"""Durable approved reward/risk thresholds keyed by broker entry order ID."""
from sqlalchemy import text
from ai_henge_fund.database.session import session_scope


def save_threshold(order_id, minimum):
    if not order_id or minimum is None:
        return
    with session_scope() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS paper_entry_rr_thresholds (
                broker_order_id VARCHAR(255) PRIMARY KEY,
                minimum_rr DOUBLE PRECISION NOT NULL
            )
        """))
        session.execute(text("""
            INSERT INTO paper_entry_rr_thresholds (broker_order_id, minimum_rr)
            VALUES (:order_id, :minimum)
            ON CONFLICT (broker_order_id) DO NOTHING
        """), {"order_id": str(order_id), "minimum": float(minimum)})


def load_threshold(order_id):
    if not order_id:
        return None
    with session_scope() as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS paper_entry_rr_thresholds (
                broker_order_id VARCHAR(255) PRIMARY KEY,
                minimum_rr DOUBLE PRECISION NOT NULL
            )
        """))
        value = session.execute(text("""
            SELECT minimum_rr FROM paper_entry_rr_thresholds
            WHERE broker_order_id = :order_id
        """), {"order_id": str(order_id)}).scalar_one_or_none()
    return float(value) if value is not None else None
