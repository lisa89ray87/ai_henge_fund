"""Metadata-focused tests for the initial trading schema models."""

from datetime import UTC
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric
from sqlalchemy.inspection import inspect

from ai_henge_fund.database.base import Base
from ai_henge_fund.database.models import (
    AgentRun,
    AgentRunStatus,
    Execution,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    Signal,
    SignalAction,
    Strategy,
)


def test_base_metadata_contains_all_initial_schema_tables() -> None:
    assert set(Base.metadata.tables) == {
        "agent_runs",
        "executions",
        "orders",
        "portfolios",
        "positions",
        "signals",
        "strategies",
    }


def test_uuid_primary_keys_use_python_uuid4_defaults() -> None:
    for model in (Portfolio, Position, Order, Execution, Strategy, Signal, AgentRun):
        identifier = model.__table__.c.id

        assert identifier.primary_key is True
        assert isinstance(identifier.default.arg(None), UUID)


def test_relationships_are_mapped_without_destructive_delete_cascades() -> None:
    assert inspect(Portfolio).relationships["positions"].mapper.class_ is Position
    assert inspect(Portfolio).relationships["orders"].mapper.class_ is Order
    assert inspect(Order).relationships["executions"].mapper.class_ is Execution
    assert inspect(Strategy).relationships["signals"].mapper.class_ is Signal
    assert inspect(Strategy).relationships["agent_runs"].mapper.class_ is AgentRun
    assert "delete" not in inspect(Portfolio).relationships["orders"].cascade


def test_enums_expose_the_expected_domain_values() -> None:
    assert set(OrderSide) == {OrderSide.BUY, OrderSide.SELL}
    assert set(OrderType) == {
        OrderType.MARKET,
        OrderType.LIMIT,
        OrderType.STOP,
        OrderType.STOP_LIMIT,
    }
    assert set(OrderStatus) == {
        OrderStatus.NEW,
        OrderStatus.PENDING,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    }
    assert set(SignalAction) == {SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD}
    assert set(AgentRunStatus) == {
        AgentRunStatus.RUNNING,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
    }


def test_financial_fields_use_decimal_numeric_precision() -> None:
    for column in (
        Portfolio.__table__.c.initial_capital,
        Position.__table__.c.quantity,
        Position.__table__.c.average_price,
        Order.__table__.c.quantity,
        Execution.__table__.c.price,
        Execution.__table__.c.commission,
        Signal.__table__.c.confidence,
    ):
        assert isinstance(column.type, Numeric)
        assert column.type.precision == 20
        assert column.type.scale == 8

    assert isinstance(Execution(commission=Decimal(0)).commission, Decimal)


def test_timestamps_are_timezone_aware() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True

    assert Portfolio.__table__.c.created_at.default.arg(None).tzinfo is UTC


def test_portfolio_symbol_constraint_and_query_indexes_exist() -> None:
    position_table = Position.__table__
    assert any(
        constraint.name == "uq_positions_portfolio_symbol"
        for constraint in position_table.constraints
    )
    assert {index.name for index in Order.__table__.indexes} == {
        "ix_orders_created_at",
        "ix_orders_portfolio_id",
        "ix_orders_status",
        "ix_orders_symbol",
    }
    assert {index.name for index in Signal.__table__.indexes} == {
        "ix_signals_generated_at",
        "ix_signals_strategy_id",
        "ix_signals_symbol",
    }
    assert {index.name for index in AgentRun.__table__.indexes} == {
        "ix_agent_runs_agent_name",
        "ix_agent_runs_started_at",
        "ix_agent_runs_status",
        "ix_agent_runs_strategy_id",
        "ix_agent_runs_symbol",
    }
