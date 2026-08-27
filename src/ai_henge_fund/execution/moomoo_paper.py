from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moomoo import OpenSecTradeContext, OrderType, SecurityFirm, TrdEnv, TrdMarket, TrdSide

from ai_henge_fund.config.settings import get_settings


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

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        settings = get_settings()
        if not settings.moomoo_paper_trading_enabled:
            raise RuntimeError(
                "Moomoo paper execution is disabled. Set "
                "MOOMOO_PAPER_TRADING_ENABLED=true to explicitly enable SIMULATE orders."
            )
        if settings.moomoo_live_trading_enabled:
            raise RuntimeError("Live Moomoo trading is disabled by project safety policy.")

        self._ctx = OpenSecTradeContext(
            host=host or settings.moomoo_opend_host,
            port=port or settings.moomoo_opend_port,
            security_firm=SecurityFirm.FUTUINC,
            filter_trdmarket=TrdMarket.US,
        )

    def close(self) -> None:
        self._ctx.close()

    def place_limit(self, *, symbol: str, side: str, quantity: int, price: float) -> MoomooPaperOrder:
        return self._place(symbol=symbol, side=side, quantity=quantity, price=price, order_type=OrderType.NORMAL)

    def place_market(self, *, symbol: str, side: str, quantity: int) -> MoomooPaperOrder:
        return self._place(symbol=symbol, side=side, quantity=quantity, price=0.0, order_type=OrderType.MARKET)

    def cancel(self, order_id: str) -> None:
        from moomoo import ModifyOrderOp

        ret, data = self._ctx.modify_order(
            ModifyOrderOp.CANCEL,
            str(order_id),
            0,
            0,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != 0:
            raise RuntimeError(f"Moomoo paper order cancellation failed: {data}")

    def _place(self, *, symbol: str, side: str, quantity: int, price: float, order_type) -> MoomooPaperOrder:
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if order_type == OrderType.NORMAL and price <= 0:
            raise ValueError("limit order price must be greater than zero")
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")

        trd_side = TrdSide.BUY if side == "BUY" else TrdSide.SELL
        ret, data = self._ctx.place_order(
            price=float(price),
            qty=int(quantity),
            code=symbol,
            trd_side=trd_side,
            order_type=order_type,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != 0:
            raise RuntimeError(f"Moomoo paper order rejected: {data}")

        row = data.iloc[0]
        order_id = str(row.get("order_id", ""))
        if not order_id:
            raise RuntimeError("Moomoo accepted the order but returned no order_id")
        status = str(row.get("order_status", "SUBMITTING")).upper()
        return MoomooPaperOrder(order_id, symbol, side, float(quantity), float(price), status, data)
