"""initial trading schema

Revision ID: aefe4d0f06dc
Revises:
Create Date: 2026-08-09 13:45:22.011469

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "aefe4d0f06dc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("initial_capital", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_id", "symbol", name="uq_positions_portfolio_symbol"),
    )
    op.create_index("ix_positions_portfolio_id", "positions", ["portfolio_id"], unique=False)
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.Enum("BUY", "SELL", name="order_side", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("order_type", sa.Enum("MARKET", "LIMIT", "STOP", "STOP_LIMIT", name="order_type", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("status", sa.Enum("NEW", "PENDING", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", name="order_status", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("broker_order_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("ix_orders_created_at", "created_at"),
        ("ix_orders_portfolio_id", "portfolio_id"),
        ("ix_orders_status", "status"),
        ("ix_orders_symbol", "symbol"),
    ):
        op.create_index(name, "orders", [column], unique=False)
    op.create_table(
        "executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("commission", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id"),
    )
    op.create_index("ix_executions_order_id", "executions", ["order_id"], unique=False)
    op.create_table(
        "ai_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("action", sa.Enum("BUY", "SELL", "HOLD", name="signal_action", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("target_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_signal_id", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_signal_id", name="uq_ai_signals_source_signal"),
    )
    for name, column in (
        ("ix_ai_signals_generated_at", "generated_at"),
        ("ix_ai_signals_source", "source"),
        ("ix_ai_signals_source_signal_id", "source_signal_id"),
        ("ix_ai_signals_strategy_id", "strategy_id"),
        ("ix_ai_signals_symbol", "symbol"),
    ):
        op.create_index(name, "ai_signals", [column], unique=False)
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("status", sa.Enum("RUNNING", "COMPLETED", "FAILED", name="agent_run_status", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, column in (
        ("ix_agent_runs_agent_name", "agent_name"),
        ("ix_agent_runs_started_at", "started_at"),
        ("ix_agent_runs_status", "status"),
        ("ix_agent_runs_strategy_id", "strategy_id"),
        ("ix_agent_runs_symbol", "symbol"),
    ):
        op.create_index(name, "agent_runs", [column], unique=False)


def downgrade() -> None:
    """Revert this revision."""
    for name in ("ix_agent_runs_symbol", "ix_agent_runs_strategy_id", "ix_agent_runs_status", "ix_agent_runs_started_at", "ix_agent_runs_agent_name"):
        op.drop_index(name, table_name="agent_runs")
    op.drop_table("agent_runs")
    for name in ("ix_ai_signals_symbol", "ix_ai_signals_strategy_id", "ix_ai_signals_source_signal_id", "ix_ai_signals_source", "ix_ai_signals_generated_at"):
        op.drop_index(name, table_name="ai_signals")
    op.drop_table("ai_signals")
    op.drop_index("ix_executions_order_id", table_name="executions")
    op.drop_table("executions")
    for name in ("ix_orders_symbol", "ix_orders_status", "ix_orders_portfolio_id", "ix_orders_created_at"):
        op.drop_index(name, table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_positions_portfolio_id", table_name="positions")
    op.drop_table("positions")
    op.drop_table("strategies")
    op.drop_table("portfolios")
