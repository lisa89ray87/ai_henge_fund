"""add append-only paper trade exit events

Revision ID: 7c4d9e2a1f60
Revises: f17c2b8a4d91
Create Date: 2026-09-03

The paper-trading lifecycle records each partial or final exit as an
immutable event. This migration makes that event table part of the managed
Alembic schema instead of relying only on runtime CREATE TABLE IF NOT EXISTS.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "7c4d9e2a1f60"
down_revision: str | Sequence[str] | None = "f17c2b8a4d91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-only paper trade exit-event table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("paper_trade_exit_events"):
        op.create_table(
            "paper_trade_exit_events",
            sa.Column("exit_id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("trade_id", sa.String(length=255), nullable=False),
            sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("exit_price", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.Column("reason", sa.String(length=32), nullable=False),
            sa.Column("broker_exit_order_id", sa.String(length=255), nullable=True),
            sa.Column("exited_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("realized_pnl", sa.Numeric(precision=20, scale=8), nullable=False),
            sa.PrimaryKeyConstraint("exit_id"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("paper_trade_exit_events")}
    if "ix_paper_trade_exit_events_trade" not in existing_indexes:
        op.create_index(
            "ix_paper_trade_exit_events_trade",
            "paper_trade_exit_events",
            ["trade_id", "exited_at"],
            unique=False,
        )


def downgrade() -> None:
    """Remove the managed exit-event table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("paper_trade_exit_events"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("paper_trade_exit_events")}
        if "ix_paper_trade_exit_events_trade" in existing_indexes:
            op.drop_index("ix_paper_trade_exit_events_trade", table_name="paper_trade_exit_events")
        op.drop_table("paper_trade_exit_events")
