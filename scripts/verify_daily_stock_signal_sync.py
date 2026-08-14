"""Prove that daily_stock_analyse signals reach the AI Henge Fund mirror."""

from sqlalchemy import text

from ai_henge_fund.database.integrations.daily_stock_analyse import (
    DAILY_STOCK_ANALYSE_SOURCE,
    sync_daily_stock_signals,
)
from ai_henge_fund.database.session import session_scope


_SOURCE_STATS_QUERY = text(
    """
    SELECT
        COUNT(*) FILTER (WHERE direction IN ('LONG', 'SHORT')) AS source_signal_count,
        COUNT(*) FILTER (WHERE direction = 'LONG') AS source_long_count,
        COUNT(*) FILTER (WHERE direction = 'SHORT') AS source_short_count,
        MAX(created_at) FILTER (WHERE direction IN ('LONG', 'SHORT')) AS source_latest_created_at
    FROM signals
    """
)

_MISSING_SOURCE_QUERY = text(
    """
    SELECT COUNT(*)
    FROM signals AS source_signals
    WHERE source_signals.direction IN ('LONG', 'SHORT')
      AND NOT EXISTS (
          SELECT 1
          FROM ai_signals AS imported
          WHERE imported.source = :source
            AND imported.source_signal_id = source_signals.signal_id::text
      )
    """
)

_IMPORTED_STATS_QUERY = text(
    """
    SELECT
        COUNT(*) AS imported_signal_count,
        COUNT(DISTINCT symbol) AS imported_symbol_count,
        MAX(generated_at) AS imported_latest_generated_at
    FROM ai_signals
    WHERE source = :source
    """
)


def main() -> int:
    with session_scope() as session:
        first_inserted = sync_daily_stock_signals(session)
        session.commit()

        second_inserted = sync_daily_stock_signals(session)
        session.commit()

        source = session.execute(_SOURCE_STATS_QUERY).one()
        missing_source_signals = session.execute(
            _MISSING_SOURCE_QUERY, {"source": DAILY_STOCK_ANALYSE_SOURCE}
        ).scalar_one()
        imported = session.execute(
            _IMPORTED_STATS_QUERY, {"source": DAILY_STOCK_ANALYSE_SOURCE}
        ).one()

    if second_inserted != 0:
        raise RuntimeError(
            "daily_stock_analyse sync is not idempotent: "
            f"second run inserted {second_inserted} rows."
        )

    if source.source_signal_count == 0:
        raise RuntimeError(
            "No LONG/SHORT signals currently exist in the source signals table; "
            "the live signal path cannot be proven by this run."
        )

    if missing_source_signals != 0:
        raise RuntimeError(
            "daily_stock_analyse signals are missing from AI Henge Fund: "
            f"{missing_source_signals} source signal(s) are not mirrored."
        )

    print("=== Daily Stock Analyse -> Neon -> AI Henge Fund verification ===")
    print(f"Source LONG/SHORT signals in Neon: {source.source_signal_count}")
    print(f"Source LONG signals: {source.source_long_count}")
    print(f"Source SHORT signals: {source.source_short_count}")
    print(f"Source latest signal: {source.source_latest_created_at}")
    print(f"AI Henge Fund imported signals: {imported.imported_signal_count}")
    print(f"AI Henge Fund imported symbols: {imported.imported_symbol_count}")
    print(f"AI Henge Fund latest imported signal: {imported.imported_latest_generated_at}")
    print(f"Source signals missing from AI Henge Fund: {missing_source_signals}")
    print(f"First sync inserted: {first_inserted}")
    print(f"Second sync inserted: {second_inserted}")
    print("RESULT: PASS — every current LONG/SHORT source signal is mirrored in AI Henge Fund.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
