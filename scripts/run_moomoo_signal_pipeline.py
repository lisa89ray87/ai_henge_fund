"""Run the live Moomoo OpenD -> deterministic -> TradingAgents -> risk pipeline.

Default mode is analysis-only. Paper execution requires explicit opt-in through
EXECUTE_PAPER=true. Live broker trading is never supported by this script.
"""

from __future__ import annotations

import os
import sys

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime
from ai_henge_fund.market_data.moomoo_opend import build_moomoo_opend_market_data
from ai_henge_fund.market_data.signal_snapshot import build_signal_snapshot
from ai_henge_fund.trading.pipeline import TradingPipeline
from ai_henge_fund.tradingagents.adapter import TradingAgentsAdapter


class GraphRunner:
    """Adapt the production TradingAgents graph result to TradingPipeline."""

    def __init__(self) -> None:
        self.runtime = TradingAgentsGraphRuntime()

    def analyze(self, payload: dict) -> dict:
        decision = self.runtime.analyze(payload)
        action = decision.action.lower()
        mapped = {"buy": "BUY", "sell": "SELL", "hold": "WAIT"}.get(action, "WAIT")
        confidence = 0.0 if decision.confidence is None else decision.confidence
        return {
            "decision": mapped,
            "confidence": confidence,
            "rationale": decision.rationale,
            "provider": decision.provider,
        }


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def main() -> int:
    symbol = os.getenv("MOOMOO_SIGNAL_SYMBOL", "US.AAPL").strip().upper()
    candle_count = int(os.getenv("MOOMOO_SIGNAL_CANDLES", "50"))
    interval = os.getenv("MOOMOO_SIGNAL_INTERVAL", "5m").strip()
    execute_paper = _truthy("EXECUTE_PAPER")

    print("=" * 72)
    print("AI Henge Fund - Moomoo OpenD Signal Pipeline")
    print("=" * 72)
    print(f"Symbol          : {symbol}")
    print(f"Candles         : {candle_count} x {interval}")
    print(f"Paper execution : {'ENABLED' if execute_paper else 'DISABLED (analysis only)'}")
    print("Live trading    : DISABLED")

    market_data = build_moomoo_opend_market_data()
    if not market_data.enabled:
        print("FAIL: MOOMOO_OPEND_ENABLED=true and MOOMOO_READ_ONLY=true are required.")
        return 2

    pipeline = TradingPipeline(ai_adapter=TradingAgentsAdapter(GraphRunner()))
    try:
        quote = market_data.get_quote(symbol)
        candles = market_data.get_candles(symbol, num=candle_count, interval=interval)
        market_state = market_data.get_market_state(symbol)

        snapshot = build_signal_snapshot(
            symbol=symbol,
            quote=quote,
            market_state=market_state,
            candles=candles,
            data_source="moomoo_opend",
        )

        result = pipeline.evaluate(snapshot, execute_paper=execute_paper)

        print(f"Data quality    : {snapshot.data_quality}")
        print(f"Market state    : {snapshot.market_state}")
        print(f"Last price      : {snapshot.last_price}")
        print(f"Deterministic   : {result.deterministic_direction}")
        print(f"AI decision     : {result.ai_decision}")
        print(f"Risk action     : {result.risk.action}")
        print(f"Risk quantity   : {result.risk.quantity:g}")
        print(f"Risk reason     : {result.risk.reason}")
        print(f"Risk checks     : {', '.join(result.risk.checks)}")

        if result.lifecycle is not None:
            print(f"Paper lifecycle : {result.lifecycle.action}")
            print(f"Paper message   : {result.lifecycle.message}")
            if result.lifecycle.broker_order_id:
                print(f"Paper order ID  : {result.lifecycle.broker_order_id}")
        elif execute_paper:
            print("Paper lifecycle : NONE")
        else:
            print("Paper lifecycle : SKIPPED (analysis-only mode)")

        print("Moomoo signal pipeline: PASS")
        return 0
    except Exception as exc:
        print(f"Moomoo signal pipeline: FAIL ({exc})")
        return 1
    finally:
        pipeline.close()
        market_data.close()


if __name__ == "__main__":
    raise SystemExit(main())
