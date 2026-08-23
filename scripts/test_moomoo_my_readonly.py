"""Read-only Moomoo MY/OpenD connectivity test.

This script deliberately uses quote APIs only. It does not import or call any
trading/execution API.

Prerequisites on the machine running the script:
- Moomoo OpenD is running and logged in.
- The official ``moomoo-api`` Python package is installed.
"""

from __future__ import annotations

import sys
from typing import Any


HOST = "127.0.0.1"
PORT = 11111
# Moomoo OpenAPI uses the MY market prefix for Bursa Malaysia securities.
SYMBOL = "MY.1155"


def main() -> int:
    try:
        from moomoo import OpenQuoteContext, RET_OK, SubType
    except ImportError as exc:
        print("SDK ERROR: the official 'moomoo-api' package is not installed.")
        print("Install it with: python -m pip install moomoo-api")
        print(f"Import error: {exc}")
        return 2

    quote_ctx = None
    try:
        print("=" * 60)
        print("Moomoo MY Read-Only Connectivity Test")
        print("=" * 60)
        print(f"OpenD endpoint: {HOST}:{PORT}")
        print(f"Test symbol:    {SYMBOL}")
        print()

        try:
            quote_ctx = OpenQuoteContext(host=HOST, port=PORT)
        except Exception as exc:
            print("OpenD connection: FAILED")
            print(f"Reason: {exc}")
            print("Make sure Moomoo OpenD is running and logged in.")
            return 3

        print("OpenD connection: PASS")

        ret_sub, sub_message = quote_ctx.subscribe(
            [SYMBOL], [SubType.QUOTE], subscribe_push=False
        )
        if ret_sub != RET_OK:
            print("Market-data subscription: FAILED")
            print(f"Reason: {sub_message}")
            print("This can indicate a market-data permission or OpenD issue.")
            return 4

        print("Market-data subscription: PASS")

        ret, data = quote_ctx.get_stock_quote([SYMBOL])
        if ret != RET_OK:
            print("Quote retrieval: FAILED")
            print(f"Reason: {data}")
            return 5

        if data is None or len(data) == 0:
            print("Quote retrieval: FAILED")
            print("Reason: OpenD returned no quote rows.")
            return 5

        row: Any = data.iloc[0]
        fields = [
            ("Market", row.get("code", SYMBOL).split(".", 1)[0]),
            ("Symbol", row.get("code", SYMBOL)),
            ("Stock Name", row.get("name", "N/A")),
            ("Last Price", row.get("last_price", "N/A")),
            ("Previous Close", row.get("prev_close_price", "N/A")),
            ("Open", row.get("open_price", "N/A")),
            ("High", row.get("high_price", "N/A")),
            ("Low", row.get("low_price", "N/A")),
            ("Volume", row.get("volume", "N/A")),
            ("Timestamp", row.get("update_time", "N/A")),
        ]

        print("\nQuote result:")
        for label, value in fields:
            print(f"  {label:16}: {value}")

        print("\nREAD-ONLY TEST: PASS")
        print("No trading/order API was called.")
        return 0

    except Exception as exc:
        print("Moomoo read-only test: FAILED")
        print(f"Reason: {exc}")
        print("No trading/order API was called by this script.")
        return 6
    finally:
        if quote_ctx is not None:
            try:
                quote_ctx.close()
            except Exception as exc:
                print(f"Warning: failed to close OpenD quote connection cleanly: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
