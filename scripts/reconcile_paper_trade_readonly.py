"""Read-only Neon + Moomoo SIMULATE paper-trade reconciliation."""
from __future__ import annotations
import argparse, json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import text
from ai_henge_fund.database.engine import get_engine
from ai_henge_fund.execution.moomoo_paper import MoomooPaperExecution

ET = ZoneInfo("America/New_York")

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--symbol", default="US.PLTR")
    a = p.parse_args()
    day = date.fromisoformat(a.date)
    symbol = a.symbol.strip().upper()
    start = datetime.combine(day, time.min, tzinfo=ET)
    end = start + timedelta(days=1)

    sql = text("""
        SELECT j.trade_id, j.symbol, j.side, j.quantity, j.entry_price,
               j.stop_price, j.target_price, j.broker_entry_order_id,
               j.opened_at, j.status, j.exit_quantity, j.exit_price,
               j.exit_reason, j.broker_exit_order_id, j.closed_at,
               j.realized_pnl AS journal_realized_pnl,
               e.exit_id, e.quantity AS event_exit_quantity,
               e.exit_price AS event_exit_price, e.reason AS event_exit_reason,
               e.broker_exit_order_id AS event_broker_exit_order_id,
               e.exited_at AS event_exited_at, e.realized_pnl AS event_realized_pnl
        FROM paper_trade_journal j
        LEFT JOIN paper_trade_exit_events e ON e.trade_id = j.trade_id
        WHERE j.symbol = :symbol
          AND ((j.opened_at >= :start AND j.opened_at < :end)
            OR (j.closed_at >= :start AND j.closed_at < :end)
            OR (e.exited_at >= :start AND e.exited_at < :end))
        ORDER BY COALESCE(e.exited_at, j.closed_at, j.opened_at), j.trade_id, e.exit_id
    """)

    # SELECT only: no CREATE/INSERT/UPDATE/DELETE and no ORM constructors that mutate schema.
    with get_engine().connect() as conn:
        db_rows = [dict(r) for r in conn.execute(sql, {
            "symbol": symbol, "start": start, "end": end
        }).mappings().all()]

    broker = MoomooPaperExecution()
    try:
        orders = broker.list_order_history()
        positions = broker.list_positions()
    finally:
        broker.close()

    def broker_day(row):
        for key in ("create_time", "updated_time"):
            raw = row.get(key) or ""
            try:
                return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(ET).date().isoformat()
            except ValueError:
                pass
        return ""

    filled = [r for r in orders if r.get("symbol") == symbol and broker_day(r) == day.isoformat()
              and float(r.get("filled_quantity", 0) or 0) > 0]

    checks = []
    for r in db_rows:
        ep = r.get("entry_price")
        eq = r.get("quantity")
        xp = r.get("event_exit_price") or r.get("exit_price")
        xq = r.get("event_exit_quantity") or r.get("exit_quantity")
        side = str(r.get("side") or "").upper()
        recorded = r.get("event_realized_pnl")
        if recorded is None:
            recorded = r.get("journal_realized_pnl")
        if None in (ep, eq, xp, xq):
            continue
        expected = ((float(xp) - float(ep)) * float(xq)
                    if side == "BUY" else (float(ep) - float(xp)) * float(xq))
        checks.append({
            "trade_id": r.get("trade_id"), "symbol": r.get("symbol"), "side": side,
            "entry_price": float(ep), "entry_quantity": float(eq),
            "exit_price": float(xp), "exit_quantity": float(xq),
            "expected_price_pnl": round(expected, 8),
            "recorded_pnl": float(recorded) if recorded is not None else None,
            "pnl_delta": round(float(recorded) - expected, 8) if recorded is not None else None,
            "entry_order_id": r.get("broker_entry_order_id"),
            "exit_order_id": r.get("event_broker_exit_order_id") or r.get("broker_exit_order_id")
        })

    payload = {
        "generated_at_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "trade_date_et": day.isoformat(), "symbol": symbol,
        "safety": {"database_access": "SELECT ONLY", "moomoo_environment": "SIMULATE",
                   "order_mutations": False, "live_trading": False},
        "neon_trade_rows": db_rows,
        "moomoo_filled_orders": filled,
        "moomoo_current_position": [r for r in positions if r.get("symbol") == symbol],
        "derived_pnl_checks": checks
    }
    out = Path("reconciliation")
    out.mkdir(exist_ok=True)
    path = out / ("paper_trade_reconciliation_" + day.isoformat() + "_" + symbol.replace(".", "_") + ".json")
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    print("\nArtifact: " + str(path))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
