"""Verify one read-only Moomoo MCP quote without exposing trading operations."""

from __future__ import annotations

import os
import sys

from ai_henge_fund.market_data.moomoo_mcp import build_moomoo_market_data


def main() -> int:
    if os.getenv("MOOMOO_MCP_ENABLED", "false").strip().lower() != "true":
        print("MOOMOO_MCP_ENABLED is not true; read-only Moomoo MCP check skipped.")
        return 0

    symbol = os.getenv("MOOMOO_VERIFY_SYMBOL", "AAPL").strip().upper()
    market_data = build_moomoo_market_data()
    quote = market_data.get_quote(symbol)

    if quote.last_price is None:
        raise RuntimeError(f"Moomoo MCP returned no last price for {symbol}.")

    print(
        f"Moomoo MCP read-only quote OK: symbol={quote.symbol} "
        f"last_price={quote.last_price} bid={quote.bid} ask={quote.ask} volume={quote.volume}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
