"""Read-only Neon daily-loss preflight; no broker access or order mutations."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import text
from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.database.session import session_scope
from ai_henge_fund.paper_trading.trade_journal import TradeJournal

def main():
    settings = get_settings()
    if settings.moomoo_live_trading_enabled or not settings.moomoo_paper_trading_enabled:
        raise RuntimeError("Expected paper-only configuration")
    # Check existing table without TradeJournal() schema creation.
    with session_scope() as session:
        session.execute(text("SELECT COUNT(*) FROM paper_trade_exit_events")).scalar_one()
    journal = object.__new__(TradeJournal)
    loss = journal.realized_loss_today_et()
    date_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York")).date()
    print(f"US/Eastern date: {date_et}; net realized loss: ${loss:.2f}; cap: ${settings.ai_henge_fund_paper_max_daily_realized_loss:.2f}")
    print("READ-ONLY NEON DAILY LOSS CHECK PASSED")

if __name__ == "__main__":
    main()
