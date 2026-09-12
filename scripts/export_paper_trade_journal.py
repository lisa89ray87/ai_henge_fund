"""Export completed paper-trade journal rows without changing the database."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import text

from ai_henge_fund.database.session import session_scope


EXPORT_COLUMNS = (
    "trade_id",
    "symbol",
    "direction",
    "entry_quantity",
    "entry_price",
    "stop_price",
    "target_price",
    "entry_timestamp",
    "exit_quantity",
    "exit_price",
    "exit_reason",
    "exit_timestamp",
    "realized_pnl",
    "broker_entry_order_id",
    "broker_exit_order_id",
)


def export_journal(output_path: Path) -> list[dict[str, object]]:
    query = text("""
        SELECT
            j.trade_id,
            j.symbol,
            CASE
                WHEN j.side = 'BUY' THEN 'LONG'
                WHEN j.side = 'SELL' THEN 'SHORT'
                ELSE j.side
            END AS direction,
            j.quantity AS entry_quantity,
            j.entry_price,
            j.stop_price,
            j.target_price,
            j.opened_at AS entry_timestamp,
            COALESCE(e.quantity, j.exit_quantity) AS exit_quantity,
            COALESCE(e.exit_price, j.exit_price) AS exit_price,
            COALESCE(e.reason, j.exit_reason) AS exit_reason,
            COALESCE(e.exited_at, j.closed_at) AS exit_timestamp,
            COALESCE(e.realized_pnl, j.realized_pnl) AS realized_pnl,
            j.broker_entry_order_id,
            COALESCE(e.broker_exit_order_id, j.broker_exit_order_id) AS broker_exit_order_id
        FROM paper_trade_journal AS j
        LEFT JOIN paper_trade_exit_events AS e
            ON e.trade_id = j.trade_id
        WHERE j.status = 'CLOSED'
           OR e.exit_id IS NOT NULL
        ORDER BY COALESCE(e.exited_at, j.closed_at), j.trade_id, e.exit_id
    """)

    with session_scope() as session:
        rows = [dict(row) for row in session.execute(query).mappings().all()]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("exports/completed_paper_trades.csv"),
        help="Local CSV destination (default: exports/completed_paper_trades.csv)",
    )
    args = parser.parse_args()

    rows = export_journal(args.output)
    trade_ids = {row["trade_id"] for row in rows}
    timestamps = [
        row["exit_timestamp"] or row["entry_timestamp"]
        for row in rows
    ]
    date_range = "none"
    if timestamps:
        date_range = f"{min(timestamps).isoformat()} to {max(timestamps).isoformat()}"
    print(f"CSV: {args.output.resolve()}")
    print(f"Rows: {len(rows)}")
    print(f"Unique trade IDs: {len(trade_ids)}")
    print(f"Date range: {date_range}")
    print("Database writes: none (SELECT only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())