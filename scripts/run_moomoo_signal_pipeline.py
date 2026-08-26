"""Run the Moomoo OpenD universe -> deterministic -> TradingAgents -> risk pipeline.

Default mode is analysis-only. Paper execution requires explicit opt-in through
EXECUTE_PAPER=true. Live broker trading is never supported by this script.
"""

from __future__ import annotations

import os

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime
from ai_henge_fund.market_data.moomoo_opend import build_moomoo_opend_market_data
from ai_henge_fund.market_data.signal_snapshot import build_signal_snapshot
from ai_henge_fund.market_data.stock_universe import get_stock_universe
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
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


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def main() -> int:
    candle_count = _int_env("MOOMOO_SIGNAL_CANDLES", 50)
    interval = os.getenv("MOOMOO_SIGNAL_INTERVAL", "5m").strip()
    execute_paper = _truthy("EXECUTE_PAPER")
    universe = get_stock_universe()
    max_ai_candidates = _int_env("MOOMOO_SIGNAL_MAX_AI_CANDIDATES", 5)
    max_paper_trades = _int_env("MOOMOO_SIGNAL_MAX_PAPER_TRADES", 1)

    print("=" * 72)
    print("AI Henge Fund - Moomoo OpenD Universe Signal Pipeline")
    print("=" * 72)
    print(f"Universe        : {len(universe)} symbols")
    print(f"Candles         : {candle_count} x {interval}")
    print(f"AI candidates   : max {max_ai_candidates}")
    print(f"Paper trades    : max {max_paper_trades}")
    print(f"Paper execution : {'ENABLED' if execute_paper else 'DISABLED (analysis only)'}")
    print("Live trading    : DISABLED")

    market_data = build_moomoo_opend_market_data()
    if not market_data.enabled:
        print("FAIL: MOOMOO_OPEND_ENABLED=true and MOOMOO_READ_ONLY=true are required.")
        return 2

    pipeline = TradingPipeline(ai_adapter=TradingAgentsAdapter(GraphRunner()))
    signal_engine = DeterministicSignalEngine()
    try:
        snapshots: list[tuple[object, object]] = []
        for symbol in universe:
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
                signal = signal_engine.evaluate(snapshot)
                print(f"SCAN {symbol}: {signal.direction} score={signal.score} state={signal.setup_state}")
                if snapshot.is_usable and signal.direction in {"LONG", "SHORT"}:
                    snapshots.append((snapshot, signal))
            except Exception as exc:
                print(f"SCAN {symbol}: SKIP ({exc})")

        snapshots.sort(key=lambda item: item[1].score, reverse=True)
        candidates = snapshots[:max_ai_candidates]
        print(f"AI analysis      : {len(candidates)} candidate(s)")

        paper_trades = 0
        analyzed = 0
        for snapshot, _signal in candidates:
            analyzed += 1
            result = pipeline.evaluate(snapshot, execute_paper=execute_paper)
            print(f"RESULT {snapshot.symbol}: deterministic={result.deterministic_direction} "
                  f"ai={result.ai_decision} risk={result.risk.action} qty={result.risk.quantity:g}")
            print(f"  reason: {result.risk.reason}")
            if result.lifecycle is not None:
                paper_trades += 1
                print(f"  paper lifecycle: {result.lifecycle.action}")
                print(f"  paper message  : {result.lifecycle.message}")
                if result.lifecycle.broker_order_id:
                    print(f"  paper order ID : {result.lifecycle.broker_order_id}")
                if paper_trades >= max_paper_trades:
                    break

        print(f"Universe scanned : {len(universe)}")
        print(f"AI analyzed      : {analyzed}")
        print(f"Paper trades     : {paper_trades}")
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
