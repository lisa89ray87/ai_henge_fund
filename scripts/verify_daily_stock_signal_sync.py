"""Verify the daily_stock_analyse signal bridge and its idempotency."""

from sqlalchemy import text

from ai_henge_fund.database.integrations.daily_stock_analyse import (
    DAILY_STOCK_ANALYSE_SOURCE,
    sync_daily_stock_signals,
)
from ai_henge_fund.database.session import session_scope


def main() -> int:
    with session_scope() as session:
        first_inserted = sync_daily_stock_signals(session)
        session.commit()

        second_inserted = sync_daily_stock_signals(session)
        session.commit()

        row = session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS signal_count,
                    MAX(generated_at) AS latest_generated_at,
                    COUNT(DISTINCT symbol) AS symbol_count
                FROM ai_signals
                WHERE source = :source
                """
            ),
            {"source": DAILY_STOCK_ANALYSE_SOURCE},
        ).one()

    if second_inserted != 0:
        raise RuntimeError(
            "daily_stock_analyse sync is not idempotent: "
            f"second run inserted {second_inserted} rows."
        )

    print(f"daily_stock_analyse first sync inserted: {first_inserted}")
    print(f"daily_stock_analyse second sync inserted: {second_inserted}")
    print(f"AI Henge Fund imported signal count: {row.signal_count}")
    print(f"AI Henge Fund imported symbol count: {row.symbol_count}")
    print(f"AI Henge Fund latest imported signal: {row.latest_generated_at}")
    print("daily_stock_analyse signal bridge verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
