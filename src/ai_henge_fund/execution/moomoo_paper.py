from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from time import sleep

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
        order = self._place(symbol=symbol, side=side, quantity=quantity, price=price, order_type=OrderType.NORMAL)
        # Every paper limit order must be broker-verified. This is especially
        # important for target exits: an accepted Python call is not enough.
        return self.verify_limit_order(order)

    def place_market(self, *, symbol: str, side: str, quantity: int) -> MoomooPaperOrder:
        return self._place(symbol=symbol, side=side, quantity=quantity, price=0.0, order_type=OrderType.MARKET)

    def verify_limit_order(self, order: MoomooPaperOrder, *, attempts: int = 3, delay_seconds: float = 0.5) -> MoomooPaperOrder:
        """Verify that a submitted SIMULATE limit order is visible at the broker.

        If the order has already filled, the returned order status is accepted
        as broker confirmation. Otherwise the order must appear in the working
        order list before this method succeeds.
        """
        expected_side = order.side.upper()
        expected_symbol = order.symbol.strip().upper()
        for attempt in range(max(1, attempts)):
            rows = self.list_open_orders()
            for row in rows:
                if (
                    row["order_id"] == order.order_id
                    and row["symbol"] == expected_symbol
                    and row["side"].endswith(expected_side)
                    and abs(float(row["price"]) - float(order.price)) < 1e-6
                ):
                    return MoomooPaperOrder(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        side=order.side,
                        quantity=order.quantity,
                        price=order.price,
                        status=str(row["status"]),
                        raw=row["raw"],
                    )

            # Query the raw broker order list so an immediately filled order is
            # not mistaken for a submission failure. This query intentionally
            # includes terminal orders unlike list_open_orders().
            ret, data = self._ctx.order_list_query(trd_env=TrdEnv.SIMULATE)
            if ret == 0 and data is not None and not data.empty:
                for _, row in data.iterrows():
                    broker_id = str(row.get("order_id", ""))
                    if broker_id == order.order_id:
                        status = str(row.get("order_status", "")).upper()
                        if status in {"FILLED_ALL", "FILLED_PART", "FILLED", "CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"}:
                            return MoomooPaperOrder(
                                order_id=order.order_id,
                                symbol=order.symbol,
                                side=order.side,
                                quantity=order.quantity,
                                price=order.price,
                                status=status,
                                raw=row.to_dict(),
                            )
            if attempt + 1 < max(1, attempts):
                sleep(max(0.0, delay_seconds))

        raise RuntimeError(
            f"Moomoo paper limit order {order.order_id} was not visible at the broker "
            f"after {max(1, attempts)} verification attempt(s)"
        )

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

    def list_positions(self) -> list[dict[str, Any]]:
        """Read authoritative US SIMULATE positions for startup reconciliation."""
        ret, data = self._ctx.position_list_query(trd_env=TrdEnv.SIMULATE)
        if ret != 0:
            raise RuntimeError(f"Moomoo paper position query failed: {data}")
        if data is None or data.empty:
            return []
        rows: list[dict[str, Any]] = []
        for _, row in data.iterrows():
            code = str(row.get("code", "")).strip().upper()
            qty = float(row.get("qty", row.get("position", 0)) or 0)
            if not code or qty == 0:
                continue
            cost = float(row.get("cost_price", row.get("average_cost", 0)) or 0)
            rows.append({"symbol": code, "quantity": qty, "average_price": cost, "raw": row.to_dict()})
        return rows

    def list_open_orders(self) -> list[dict[str, Any]]:
        """Read currently working SIMULATE orders without changing them."""
        ret, data = self._ctx.order_list_query(trd_env=TrdEnv.SIMULATE)
        if ret != 0:
            raise RuntimeError(f"Moomoo paper order query failed: {data}")
        if data is None or data.empty:
            return []
        terminal = {"FILLED_ALL", "CANCELLED_ALL", "FAILED", "DELETED", "DISABLED", "FILL_CANCELLED"}
        rows: list[dict[str, Any]] = []
        for _, row in data.iterrows():
            status = str(row.get("order_status", "")).upper()
            if status in terminal:
                continue
            rows.append({
                "order_id": str(row.get("order_id", "")),
                "symbol": str(row.get("code", "")).strip().upper(),
                "side": str(row.get("trd_side", row.get("side", ""))).upper(),
                "price": float(row.get("price", 0) or 0),
                "quantity": float(row.get("qty", 0) or 0),
                "status": status,
                "raw": row.to_dict(),
            })
        return rows

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
