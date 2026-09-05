from __future__ import annotations

import sys

import moomoo
from moomoo import OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

HOST = "127.0.0.1"
PORT = 11111


def main() -> int:
    print("=" * 72)
    print("AI Henge Fund - Moomoo OpenD Capability Probe (READ ONLY)")
    print("=" * 72)
    print(f"Python          : {sys.version.split()[0]}")
    print(f"moomoo-api      : {getattr(moomoo, '__version__', 'NOT EXPOSED')}")
    print(f"OpenD endpoint  : {HOST}:{PORT}")
    print("Order placement : NOT CALLED")
    print("=" * 72)

    # SDK surface inspection only. This does not connect or place an order.
    print("SDK capabilities")
    session = getattr(moomoo, "Session", None)
    order_type = getattr(moomoo, "OrderType", None)
    if session is not None:
        print("Session enum    :", [name for name in dir(session) if not name.startswith("_")])
    else:
        print("Session enum    : NOT EXPOSED")
    if order_type is not None:
        print("OrderType enum  :", [name for name in dir(order_type) if not name.startswith("_")])
    else:
        print("OrderType enum  : NOT EXPOSED")

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

        print("\nAccount capability")
        print("Account-list query: PASS")
        print("Columns           :", ", ".join(data.columns.tolist()))

        simulate = data[data["trd_env"] == TrdEnv.SIMULATE]
        print(f"SIMULATE accounts : {len(simulate)}")
        if simulate.empty:
            print("US SIMULATE      : NOT FOUND")
            return 2

        print("\nSIMULATE account rows:")
        print(simulate.to_string(index=False))

        authority_col = "trdmarket_auth" if "trdmarket_auth" in simulate.columns else None
        if authority_col:
            print(f"US authority col  : {authority_col}")
            print("US authority rows :")
            us = simulate[simulate[authority_col].astype(str).str.upper().str.contains("US")]
            print(us.to_string(index=False) if not us.empty else "NONE")
        else:
            print("US authority col  : NOT RETURNED")

        print("\nRESULT")
        print("- OpenD connection/account query is working.")
        print("- The actual installed SDK version is printed above.")
        print("- The actual SIMULATE account row(s) are printed above.")
        print("- No order, cancellation, position mutation, or other trading action was performed.")
        return 0
    finally:
        ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
