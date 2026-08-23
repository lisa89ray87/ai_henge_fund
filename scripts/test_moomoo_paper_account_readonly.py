from __future__ import annotations

import sys

from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

HOST = "127.0.0.1"
PORT = 11111


def main() -> int:
    print("=" * 60)
    print("AI Henge Fund - Moomoo Paper Account Read-Only Test")
    print("=" * 60)
    print(f"OpenD endpoint : {HOST}:{PORT}")
    print("Order API      : NOT CALLED")

    ctx = OpenSecTradeContext(
        host=HOST,
        port=PORT,
        security_firm=SecurityFirm.FUTUINC,
        filter_trdmarket=TrdMarket.US,
    )
    try:
        ret, data = ctx.get_acc_list()
        if ret != 0:
            print(f"Account-list query: FAIL ({ret})")
            print(data)
            return 1

        print("Account-list query: PASS")
        simulate = data[data["trd_env"] == TrdEnv.SIMULATE]
        us = simulate[simulate["trdmarket"] == TrdMarket.US]

        print(f"SIMULATE accounts : {len(simulate)}")
        print(f"US SIMULATE       : {len(us)}")
        if not us.empty:
            print("US paper account detected: PASS")
            print(us.to_string(index=False))
            print("PAPER ACCOUNT TEST: PASS")
            return 0

        print("US paper account detected: NO")
        print("PAPER ACCOUNT TEST: NOT AVAILABLE")
        return 2
    finally:
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
