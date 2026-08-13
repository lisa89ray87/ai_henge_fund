"""Import persisted signals from daily_stock_analyse into AI Henge Fund."""

from ai_henge_fund.database.integrations.daily_stock_analyse import sync_daily_stock_signals
from ai_henge_fund.database.session import session_scope


def main() -> int:
    with session_scope() as session:
        inserted = sync_daily_stock_signals(session)
    print(f"daily_stock_analyse signals imported: {inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
