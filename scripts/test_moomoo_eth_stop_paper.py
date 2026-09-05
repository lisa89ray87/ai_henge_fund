"""Safe paper-only probe for a US ETH stop order.

This script is explicitly opt-in and uses TrdEnv.SIMULATE only. It submits
one tiny STOP_LIMIT order far from the market, then immediately cancels it.
It never enables or calls live trading.

Run only while OpenD is connected to the intended paper account:
    MOOMOO_ETH_STOP_PAPER_TEST=1 python scripts/test_moomoo_eth_stop_paper.py

The order is deliberately configured so it should not trigger immediately.
The test answers whether the paper account accepts STOP_LIMIT with Session.ETH.
"""

from __future__ import annotations

import os
import sys
import time

from moomoo import (
    OpenSecTradeContext,
    OrderType,
    SecurityFirm,
    Session,
    TrdEnv,
    TrdMarket,
    TrdSide,
)

HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
SYMBOL = os.getenv("MOOMOO_ETH_STOP_TEST_SYMBOL", "US.AAPL")
QTY = float(os.getenv("MOOMOO_ETH_STOP_TEST_QTY", "1"))
# For a long-position protection test, a stop below market is required.
# $1 is intentionally far below AAPL's market price for this capability probe.
AUX_PRICE = float(os.getenv("MOOMOO_ETH_STOP_TEST_AUX_PRICE", "1.00"))
LIMIT_PRICE = float(os.getenv("MOOMOO_ETH_STOP_TEST_LIMIT_PRICE", "0.90"))


def main() -> int:
    print("=" * 72)
    print("AI Henge Fund - Moomoo PAPER ETH STOP_LIMIT Capability Test")
    print("=" * 72)
    print(f"Python          : {sys.version.split()[0]}")
    print(f"OpenD endpoint  : {HOST}:{PORT}")
    print(f"Symbol          : {SYMBOL}")
    print(f"Quantity        : {QTY}")
    print(f"Stop trigger    : {AUX_PRICE}")
    print(f"Limit price     : {LIMIT_PRICE}")
    print("Trading env     : SIMULATE ONLY")
    print("Session         : ETH")
    print("Order type      : STOP_LIMIT")
    print("Side            : SELL")
    print("Live trading    : NEVER CALLED")
    print("=" * 72)

    if os.getenv("MOOMOO_ETH_STOP_PAPER_TEST") != "1":
        print("SAFETY STOP: set MOOMOO_ETH_STOP_PAPER_TEST=1 to opt in.")
        return 2
    if QTY <= 0 or AUX_PRICE <= 0 or LIMIT_PRICE <= 0:
        print("SAFETY STOP: quantity and prices must be positive.")
        return 2
    if LIMIT_PRICE > AUX_PRICE:
        print("SAFETY STOP: for this SELL stop-limit probe, limit price must be <= stop trigger.")
        return 2

    ctx = OpenSecTradeContext(
        host=HOST,
        port=PORT,
        security_firm=SecurityFirm.FUTUINC,
        filter_trdmarket=TrdMarket.US,
    )

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
        print("\nSubmitting ONE paper ETH STOP_LIMIT order...")

        ret, result = ctx.place_order(
            price=LIMIT_PRICE,
            qty=QTY,
            code=SYMBOL,
            trd_side=TrdSide.SELL,
            order_type=OrderType.STOP_LIMIT,
            aux_price=AUX_PRICE,
            trd_env=TrdEnv.SIMULATE,
            acc_id=acc_id,
            session=Session.ETH,
        )

        print(f"place_order ret : {ret}")
        print(result)
        if ret != 0:
            print("\nRESULT: ETH STOP_LIMIT paper order was REJECTED.")
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
            modify_order_op="CANCEL",
            order_id=str(order_id),
            qty=QTY,
            price=LIMIT_PRICE,
            trd_env=TrdEnv.SIMULATE,
            acc_id=acc_id,
        )
        print(f"cancel_order ret: {cancel_ret}")
        print(cancel_data)
        if cancel_ret == 0:
            print("\nRESULT: ETH STOP_LIMIT paper order ACCEPTED and cancellation succeeded.")
            return 0
        print("\nRESULT: ETH STOP_LIMIT paper order was accepted, but cancellation failed.")
        return 1
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
