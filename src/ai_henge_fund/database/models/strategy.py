"""Strategy persistence model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_henge_fund.database.base import Base, utc_now

if TYPE_CHECKING:
    from ai_henge_fund.database.models.agent_run import AgentRun
    from ai_henge_fund.database.models.signal import Signal


class Strategy(Base):
    """A versioned investment strategy that can emit signals and agent runs."""

    __tablename__ = "strategies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    signals: Mapped[list[Signal]] = relationship(back_populates="strategy")
    agent_runs: Mapped[list[AgentRun]] = relationship(back_populates="strategy")
