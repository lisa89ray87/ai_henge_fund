"""Safe paper-only probe for a US ETH limit order.

This script is intentionally opt-in and never uses the live environment.
It submits one tiny LIMIT order to the US SIMULATE account with Session.ETH,
then immediately cancels it if accepted. It does not modify positions unless
Moomoo unexpectedly fills the limit order before cancellation.

Run only while OpenD is connected to the intended paper account.
Enable explicitly with:
    MOOMOO_ETH_PAPER_TEST=1 python scripts/test_moomoo_eth_limit_paper.py
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
SYMBOL = os.getenv("MOOMOO_ETH_TEST_SYMBOL", "US.AAPL")
QTY = float(os.getenv("MOOMOO_ETH_TEST_QTY", "1"))
PRICE = float(os.getenv("MOOMOO_ETH_TEST_PRICE", "1.00"))


def main() -> int:
    print("=" * 72)
    print("AI Henge Fund - Moomoo PAPER ETH LIMIT Capability Test")
    print("=" * 72)
    print(f"Python          : {sys.version.split()[0]}")
    print(f"OpenD endpoint  : {HOST}:{PORT}")
    print(f"Symbol          : {SYMBOL}")
    print(f"Quantity        : {QTY}")
    print(f"Limit price     : {PRICE}")
    print("Trading env     : SIMULATE ONLY")
    print("Session         : ETH")
    print("Order type      : NORMAL/LIMIT")
    print("Live trading    : NEVER CALLED")
    print("=" * 72)

    if os.getenv("MOOMOO_ETH_PAPER_TEST") != "1":
        print("SAFETY STOP: set MOOMOO_ETH_PAPER_TEST=1 to opt in.")
        return 2
    if QTY <= 0 or PRICE <= 0:
        print("SAFETY STOP: quantity and price must be positive.")
        return 2

    ctx = OpenSecTradeContext(
        host=HOST,
        port=PORT,
        security_firm=SecurityFirm.FUTUINC,
        filter_trdmarket=TrdMarket.US,
    )

    order_id = None
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
        print("\nSubmitting ONE paper ETH LIMIT order...")

        ret, result = ctx.place_order(
            price=PRICE,
            qty=QTY,
            code=SYMBOL,
            trd_side=TrdSide.BUY,
            order_type=OrderType.NORMAL,
            trd_env=TrdEnv.SIMULATE,
            acc_id=acc_id,
            session=Session.ETH,
        )

        print(f"place_order ret : {ret}")
        print(result)
        if ret != 0:
            print("\nRESULT: ETH LIMIT paper order was REJECTED.")
            print("This is a server/account capability result; no order was created.")
            return 1

        if "order_id" in result.columns:
            order_id = result.iloc[0]["order_id"]
        print(f"Accepted order id: {order_id}")

        # Give the broker a brief moment to register the order, then cancel it.
        time.sleep(1)
        if order_id is not None:
            print("Cancelling the test order immediately...")
            cancel_ret, cancel_data = ctx.modify_order(
                modify_order_op="CANCEL",
                order_id=str(order_id),
                qty=QTY,
                price=PRICE,
                trd_env=TrdEnv.SIMULATE,
                acc_id=acc_id,
            )
            print(f"cancel_order ret: {cancel_ret}")
            print(cancel_data)
            if cancel_ret == 0:
                print("\nRESULT: ETH LIMIT paper order ACCEPTED and cancellation succeeded.")
                return 0
            print("\nRESULT: ETH LIMIT paper order was accepted, but cancellation failed.")
            return 1

        print("\nRESULT: order accepted but no order_id was returned; manual verification required.")
        return 1
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
