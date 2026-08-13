"""ensure ai_signals exists for databases already carrying the base schema

Revision ID: f17c2b8a4d91
Revises: ce529a67fc63
Create Date: 2026-08-13

This is an additive drift-repair revision. The original initial revision also
creates ai_signals for fresh databases, so this revision is intentionally
idempotent and does nothing when that table already exists.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f17c2b8a4d91"
down_revision: str | Sequence[str] | None = "ce529a67fc63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create only the missing AI Henge Fund signal table and normalize its constraint metadata."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("ai_signals"):
        op.create_table(
            "ai_signals",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("strategy_id", sa.Uuid(), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column(
                "action",
                sa.Enum(
                    "BUY",
                    "SELL",
                    "HOLD",
                    name="signal_action",
                    native_enum=False,
                    create_constraint=False,
                ),
                nullable=False,
            ),
            sa.Column("confidence", sa.Numeric(precision=20, scale=8), nullable=True),
            sa.Column("target_price", sa.Numeric(precision=20, scale=8), nullable=True),
            sa.Column("reasoning", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("source_signal_id", sa.String(length=128), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "source",
                "source_signal_id",
                name="uq_ai_signals_source_signal",
            ),
        )

    # The historical initial revision created a CHECK constraint for this
    # non-native enum. The ORM model intentionally does not, so remove it when
    # present to make the managed schema converge cleanly.
    check_constraints = inspector.get_check_constraints("ai_signals")
    for constraint in check_constraints:
        if constraint.get("name") == "signal_action":
            op.drop_constraint("signal_action", "ai_signals", type_="check")

    existing_indexes = {index["name"] for index in inspector.get_indexes("ai_signals")}
    for name, column in (
        ("ix_ai_signals_generated_at", "generated_at"),
        ("ix_ai_signals_source", "source"),
        ("ix_ai_signals_source_signal_id", "source_signal_id"),
        ("ix_ai_signals_strategy_id", "strategy_id"),
        ("ix_ai_signals_symbol", "symbol"),
    ):
        if name not in existing_indexes:
            op.create_index(name, "ai_signals", [column], unique=False)


def downgrade() -> None:
    """Leave ai_signals intact because it belongs to the base schema revision."""
    # The base revision already owns this table for fresh installations.
    # A no-op downgrade avoids dropping a table that may have been created by
    # the base revision rather than by this drift-repair revision.
    return
