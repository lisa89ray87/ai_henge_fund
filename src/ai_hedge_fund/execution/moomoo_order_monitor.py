from __future__ import annotations

from dataclasses import dataclass
from time import sleep

from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket


FILLED_ALL = "FILLED_ALL"
FILLED_PART = "FILLED_PART"
TERMINAL_STATUSES = {
    FILLED_ALL,
    "CANCELLED_ALL",
    "CANCELLED_PART",
    "FAILED",
    "DISABLED",
    "DELETED",
    "FILL_CANCELLED",
}


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
        ret, data = self._ctx.order_list_query(
            order_id=str(order_id),
            order_market=TrdMarket.US,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != 0:
            raise RuntimeError(f"Moomoo order query failed: {data}")

        if data.empty:
            raise LookupError(f"Paper order {order_id} was not found")

        row = data.iloc[0]
        status = str(row.get("order_status", "UNKNOWN")).upper()
        submitted = _float(row.get("qty"), default=0.0)

        # Current Moomoo SDK fields are dealt_qty/dealt_avg_price.
        # Legacy aliases are accepted for older local SDK/OpenD combinations.
        filled = _float_first(row, ("dealt_qty", "qty_filled", "fill_qty"), default=None)
        if filled is None:
            filled = submitted if status == FILLED_ALL else 0.0
        filled = max(0.0, filled)

        remaining = _float_first(row, ("qty_remaining", "remaining_qty"), default=None)
        if remaining is None:
            remaining = max(0.0, submitted - filled)
        remaining = max(0.0, remaining)

        avg = _float_first(row, ("dealt_avg_price", "fill_avg_price", "avg_price"), default=None)
        average_price = avg if avg is not None and avg > 0 else None

        return MoomooOrderStatus(
            order_id=str(order_id),
            status=status,
            submitted_quantity=submitted,
            filled_quantity=filled,
            remaining_quantity=remaining,
            average_price=average_price,
        )

    def wait_for_terminal(
        self,
        order_id: str,
        timeout_seconds: int = 30,
        interval_seconds: float = 2.0,
    ) -> MoomooOrderStatus:
        elapsed = 0.0
        latest = self.get(order_id)
        while latest.status not in TERMINAL_STATUSES and elapsed < timeout_seconds:
            sleep(interval_seconds)
            elapsed += interval_seconds
            latest = self.get(order_id)
        return latest


def _float(value: object, *, default: float) -> float:
    if value is None or value == "" or str(value).lower() == "nan":
        return default
    return float(value)


def _float_first(row: object, names: tuple[str, ...], *, default: float | None) -> float | None:
    for name in names:
        try:
            value = row.get(name)  # type: ignore[union-attr]
        except AttributeError:
            value = None
        if value is None or value == "" or str(value).lower() == "nan":
            continue
        return float(value)
    return default
