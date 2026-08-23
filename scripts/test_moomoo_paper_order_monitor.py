from __future__ import annotations

import os
import sys

from ai_hedge_fund.execution.moomoo_order_monitor import MoomooPaperOrderMonitor


def main() -> int:
    order_id = os.getenv("AI_HEDGE_FUND_MOOMOO_TEST_ORDER_ID")
    if not order_id:
        print("ORDER MONITOR TEST: SKIPPED")
        print("Set AI_HEDGE_FUND_MOOMOO_TEST_ORDER_ID first.")
        return 0

    monitor = MoomooPaperOrderMonitor()
    try:
        result = monitor.get(order_id)
        print("=" * 60)
        print("AI Henge Fund - Moomoo Paper Order Monitor")
        print("Environment : MOOMOO SIMULATE ONLY")
        print(f"Order ID   : {result.order_id}")
        print(f"Status     : {result.status}")
        print(f"Filled Qty : {result.filled_quantity}")
        print(f"Avg Price  : {result.average_price}")
        print("ORDER MONITOR TEST: PASS")
        return 0
    except Exception as exc:
        print(f"ORDER MONITOR TEST: FAIL ({exc})")
        return 1
    finally:
        monitor.close()


if __name__ == "__main__":
    sys.exit(main())
