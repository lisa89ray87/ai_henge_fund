from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from moomoo import OpenSecTradeContext, OrderStatus, SecurityFirm, TrdEnv, TrdMarket


@dataclass(frozen=True)
class MoomooOrderStatus:
    order_id: str
    status: str
    filled_quantity: float
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
        filled = float(row.get("qty", 0) or 0) - float(row.get("qty_remaining", 0) or 0)
        avg = row.get("fill_avg_price")
        return MoomooOrderStatus(
            order_id=str(order_id),
            status=str(row.get("order_status", "UNKNOWN")),
            filled_quantity=max(0.0, filled),
            average_price=float(avg) if avg not in (None, "", "nan") else None,
        )

    def wait_for_terminal(self, order_id: str, timeout_seconds: int = 30, interval_seconds: float = 2.0) -> MoomooOrderStatus:
        terminal = {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED_ALL,
            OrderStatus.CANCELLED_PART,
            OrderStatus.FAILED,
            OrderStatus.DISABLED,
        }
        elapsed = 0.0
        latest = self.get(order_id)
        while latest.status not in {str(x) for x in terminal} and elapsed < timeout_seconds:
            sleep(interval_seconds)
            elapsed += interval_seconds
            latest = self.get(order_id)
        return latest
