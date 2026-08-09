"""AI agent execution audit persistence model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_henge_fund.database.base import Base, utc_now

if TYPE_CHECKING:
    from ai_henge_fund.database.models.strategy import Strategy


class AgentRunStatus(StrEnum):
    """Permitted agent-run lifecycle states."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentRun(Base):
    """An auditable invocation of an AI analysis agent."""

    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID | None] = mapped_column(ForeignKey("strategies.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status", native_enum=False, create_constraint=False),
        nullable=False,
        default=AgentRunStatus.RUNNING,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    strategy: Mapped[Strategy | None] = relationship(back_populates="agent_runs")
