"""Exercise the AI Henge Fund Moomoo OpenD adapter without trading APIs."""

from __future__ import annotations

import os

from ai_henge_fund.market_data import MoomooMarketData, MoomooOpenDTransport


def main() -> int:
    symbol = os.getenv("MOOMOO_VERIFY_SYMBOL", "AAPL").strip().upper()
    transport = MoomooOpenDTransport()
    market_data = MoomooMarketData(transport, enabled=True)

    try:
        quote = market_data.get_quote(symbol)
        candles = market_data.get_candles(symbol, num=3, interval="5m")
        state = market_data.get_market_state(symbol)

        print("=" * 60)
        print("AI Henge Fund - Moomoo OpenD Read-Only Provider Test")
        print("=" * 60)
        print(f"OpenD endpoint : {transport.host}:{transport.port}")
        print(f"Symbol         : {quote.symbol}")
        print(f"Last price     : {quote.last_price}")
        print(f"Bid / Ask      : {quote.bid} / {quote.ask}")
        print(f"Volume         : {quote.volume}")
        print(f"Market state   : {state.state}")
        print(f"Candles        : {len(candles)} x 5m")
        if candles:
            latest = candles[-1]
            print(
                "Latest candle  : "
                f"{latest.time} O={latest.open} H={latest.high} "
                f"L={latest.low} C={latest.close} V={latest.volume}"
            )
        print("\nREAD-ONLY PROVIDER TEST: PASS")
        print("No trading/order/account API was called.")
        return 0
    except Exception as exc:
        print("READ-ONLY PROVIDER TEST: FAILED")
        print(f"Reason: {exc}")
        print("No trading/order/account API was called by this script.")
        return 1
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
