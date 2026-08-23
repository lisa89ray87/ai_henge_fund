from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket


FILLED = "FILLED"
TERMINAL_STATUSES = {"FILLED", "CANCELLED_ALL", "CANCELLED_PART", "FAILED", "DISABLED"}


@dataclass(frozen=True)
class MoomooOrderStatus:
    order_id: str
    status: str
    submitted_quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_price: float | None


class MoomooPaperOrderMonitor:
    """Read-only monitor for orders submitted to the US SIMULATE account."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111) -> None:
        self._ctx = OpenSecTradeContext(
            host=host,
            port=port,
            security_firm=SecurityFirm.FUTUINC,
            filter_trdmarket=TrdMarket.US,
        )

    def close(self) -> None:
        self._ctx.close()

    def get(self, order_id: str) -> MoomooOrderStatus:
        ret, data = self._ctx.order_list_query(trd_env=TrdEnv.SIMULATE)
        if ret != 0:
            raise RuntimeError(f"Moomoo order query failed: {data}")

        rows = data[data["order_id"].astype(str) == str(order_id)]
        if rows.empty:
            raise LookupError(f"Paper order {order_id} was not found")

        row = rows.iloc[0]
        status = str(row.get("order_status", "UNKNOWN")).upper()
        submitted = float(row.get("qty", 0) or 0)
        raw_filled = row.get("qty_filled")
        if raw_filled not in (None, "", "nan"):
            filled = max(0.0, float(raw_filled))
        elif status == FILLED:
            filled = submitted
        else:
            filled = 0.0

        remaining_raw = row.get("qty_remaining")
        remaining = (max(0.0, float(remaining_raw)) if remaining_raw not in (None, "", "nan")
                     else max(0.0, submitted - filled))
        avg = row.get("fill_avg_price")
        average_price = float(avg) if avg not in (None, "", "nan") else None
        return MoomooOrderStatus(
            order_id=str(order_id),
            status=status,
            submitted_quantity=submitted,
            filled_quantity=filled,
            remaining_quantity=remaining,
            average_price=average_price,
        )

    def wait_for_terminal(self, order_id: str, timeout_seconds: int = 30, interval_seconds: float = 2.0) -> MoomooOrderStatus:
        elapsed = 0.0
        latest = self.get(order_id)
        while latest.status not in TERMINAL_STATUSES and elapsed < timeout_seconds:
            sleep(interval_seconds)
            elapsed += interval_seconds
            latest = self.get(order_id)
        return latest
