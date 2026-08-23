from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket, TrdSide, OrderType


@dataclass(frozen=True)
class MoomooPaperOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    status: str
    raw: Any


class MoomooPaperExecution:
    """Execution adapter locked to Moomoo's US SIMULATE environment."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111) -> None:
        self._ctx = OpenSecTradeContext(
            host=host,
            port=port,
            security_firm=SecurityFirm.FUTUINC,
            filter_trdmarket=TrdMarket.US,
        )

    def close(self) -> None:
        self._ctx.close()

    def place_limit(self, *, symbol: str, side: str, quantity: int, price: float) -> MoomooPaperOrder:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be greater than zero")
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")

        trd_side = TrdSide.BUY if side == "BUY" else TrdSide.SELL
        ret, data = self._ctx.place_order(
            price=float(price),
            qty=int(quantity),
            code=symbol,
            trd_side=trd_side,
            order_type=OrderType.NORMAL,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != 0:
            raise RuntimeError(f"Moomoo paper order rejected: {data}")

        row = data.iloc[0]
        order_id = str(row.get("order_id", ""))
        status = str(row.get("order_status", "SUBMITTED"))
        return MoomooPaperOrder(order_id, symbol, side, float(quantity), float(price), status, data)
