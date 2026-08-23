from __future__ import annotations

import os
import sys

from ai_hedge_fund.execution.moomoo_paper import MoomooPaperExecution


# Safety: this script requires explicit opt-in before submitting a paper order.
# It can never select TrdEnv.REAL; the adapter is hard-coded to SIMULATE.
def main() -> int:
    print("=" * 60)
    print("AI Henge Fund - Moomoo Paper Order Test")
    print("=" * 60)
    print("Environment : MOOMOO SIMULATE ONLY")
    print("LIVE orders : DISABLED")

    if os.getenv("AI_HEDGE_FUND_CONFIRM_MOOMOO_PAPER_ORDER") != "YES":
        print("PAPER ORDER TEST: SKIPPED")
        print("Set AI_HEDGE_FUND_CONFIRM_MOOMOO_PAPER_ORDER=YES to explicitly opt in.")
        return 0

    symbol = os.getenv("AI_HEDGE_FUND_PAPER_TEST_SYMBOL", "US.AAPL")
    quantity = int(os.getenv("AI_HEDGE_FUND_PAPER_TEST_QTY", "1"))
    price = float(os.getenv("AI_HEDGE_FUND_PAPER_TEST_PRICE", "0"))
    if price <= 0:
        print("PAPER ORDER TEST: ABORTED")
        print("Set AI_HEDGE_FUND_PAPER_TEST_PRICE to a valid limit price.")
        return 2

    executor = MoomooPaperExecution()
    try:
        result = executor.place_limit(symbol=symbol, side="BUY", quantity=quantity, price=price)
        print("Paper order submission: PASS")
        print(f"Order ID : {result.order_id}")
        print(f"Status   : {result.status}")
        print(f"Symbol   : {result.symbol}")
        print(f"Qty      : {result.quantity}")
        print(f"Price    : {result.price}")
        return 0
    except Exception as exc:
        print(f"Paper order submission: FAIL ({exc})")
        return 1
    finally:
        executor.close()


if __name__ == "__main__":
    sys.exit(main())
