from __future__ import annotations

import sys

from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

HOST = "127.0.0.1"
PORT = 11111


def _has_us_authority(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return TrdMarket.US in value or "US" in value
    return value == TrdMarket.US or str(value).upper() == "US"


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
        print("Returned columns :", ", ".join(data.columns.tolist()))

        simulate = data[data["trd_env"] == TrdEnv.SIMULATE]
        authority_col = "trdmarket_auth" if "trdmarket_auth" in data.columns else None
        if authority_col is None:
            print("US authority column: NOT RETURNED")
            print("Raw account list:")
            print(simulate.to_string(index=False))
            print("PAPER ACCOUNT TEST: INCONCLUSIVE")
            return 2

        us = simulate[simulate[authority_col].apply(_has_us_authority)]

        print(f"SIMULATE accounts : {len(simulate)}")
        print(f"US SIMULATE       : {len(us)}")
        if not us.empty:
            print("US paper account detected: PASS")
            print(us.to_string(index=False))
            print("PAPER ACCOUNT TEST: PASS")
            return 0

        print("US paper account detected: NO")
        print("PAPER ACCOUNT TEST: NOT AVAILABLE")
        print("SIMULATE accounts returned:")
        print(simulate.to_string(index=False))
        return 2
    finally:
        ctx.close()


if __name__ == "__main__":
    sys.exit(main())
