"""AI and strategy signal persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_henge_fund.database.base import Base, utc_now

if TYPE_CHECKING:
    from ai_henge_fund.database.models.strategy import Strategy


class SignalAction(StrEnum):
    """Permitted signal actions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Signal(Base):
    """A time-stamped recommendation produced by a strategy or AI agent."""

    __tablename__ = "signals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID] = mapped_column(
        ForeignKey("strategies.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[SignalAction] = mapped_column(
        Enum(SignalAction, name="signal_action", native_enum=False, create_constraint=False),
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    reasoning: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    strategy: Mapped[Strategy] = relationship(back_populates="signals")
