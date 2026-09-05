"""Safe paper-only probe for a US ETH STOP order.

Explicitly opt in with MOOMOO_ETH_PLAIN_STOP_PAPER_TEST=1.
Uses TrdEnv.SIMULATE only, submits one SELL STOP far below market,
then immediately cancels if accepted. Never calls live trading.
"""
from __future__ import annotations

import os
import sys
import time

from moomoo import OpenSecTradeContext, OrderType, SecurityFirm, Session, TrdEnv, TrdMarket, TrdSide

HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
SYMBOL = os.getenv("MOOMOO_ETH_STOP_TEST_SYMBOL", "US.AAPL")
QTY = float(os.getenv("MOOMOO_ETH_STOP_TEST_QTY", "1"))
AUX_PRICE = float(os.getenv("MOOMOO_ETH_STOP_TEST_AUX_PRICE", "1.00"))


def main() -> int:
    print("=" * 72)
    print("AI Henge Fund - Moomoo PAPER ETH STOP Capability Test")
    print("=" * 72)
    print(f"Python          : {sys.version.split()[0]}")
    print(f"OpenD endpoint  : {HOST}:{PORT}")
    print(f"Symbol          : {SYMBOL}")
    print(f"Quantity        : {QTY}")
    print(f"Stop trigger    : {AUX_PRICE}")
    print("Trading env     : SIMULATE ONLY")
    print("Session         : ETH")
    print("Order type      : STOP")
    print("Side            : SELL")
    print("Live trading    : NEVER CALLED")
    print("=" * 72)

    if os.getenv("MOOMOO_ETH_PLAIN_STOP_PAPER_TEST") != "1":
        print("SAFETY STOP: set MOOMOO_ETH_PLAIN_STOP_PAPER_TEST=1 to opt in.")
        return 2
    if QTY <= 0 or AUX_PRICE <= 0:
        print("SAFETY STOP: quantity and stop trigger must be positive.")
        return 2

    ctx = OpenSecTradeContext(host=HOST, port=PORT, security_firm=SecurityFirm.FUTUINC, filter_trdmarket=TrdMarket.US)
    try:
        ret, data = ctx.get_acc_list()
        if ret != 0:
            print(f"Account-list query: FAIL ret={ret}")
            print(data)
            return 1
        sim = data[data["trd_env"] == TrdEnv.SIMULATE]
        us = sim[sim["trdmarket_auth"].apply(lambda x: "US" in str(x))]
        if us.empty:
            print("SAFETY STOP: no active US SIMULATE account found.")
            return 1
        row = us.iloc[0]
        acc_id = int(row["acc_id"])
        print(f"Using SIMULATE account: {acc_id}")
        print(f"Account type      : {row['acc_type']}")
        print(f"Sim account type  : {row['sim_acc_type']}")
        print("\nSubmitting ONE paper ETH STOP order...")
        ret, result = ctx.place_order(
            price=0,
            qty=QTY,
            code=SYMBOL,
            trd_side=TrdSide.SELL,
            order_type=OrderType.STOP,
            aux_price=AUX_PRICE,
            trd_env=TrdEnv.SIMULATE,
            acc_id=acc_id,
            session=Session.ETH,
        )
        print(f"place_order ret : {ret}")
        print(result)
        if ret != 0:
            print("\nRESULT: ETH STOP paper order was REJECTED.")
            print("This is the server/account capability result; no accepted order was created.")
            return 1
        if "order_id" not in result.columns:
            print("\nRESULT: order accepted but no order_id was returned; manual verification required.")
            return 1
        order_id = result.iloc[0]["order_id"]
        print(f"Accepted order id: {order_id}")
        time.sleep(1)
        print("Cancelling the test order immediately...")
        cancel_ret, cancel_data = ctx.modify_order(
            modify_order_op="CANCEL", order_id=str(order_id), qty=QTY, price=0,
            trd_env=TrdEnv.SIMULATE, acc_id=acc_id,
        )
        print(f"cancel_order ret: {cancel_ret}")
        print(cancel_data)
        if cancel_ret == 0:
            print("\nRESULT: ETH STOP paper order ACCEPTED and cancellation succeeded.")
            return 0
        print("\nRESULT: ETH STOP paper order was accepted, but cancellation failed.")
        return 1
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
