"""Run the Moomoo OpenD universe -> deterministic -> TradingAgents -> risk pipeline."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ai_henge_fund.agents.tradingagents_bridge import TradingAgentsGraphRuntime
from ai_henge_fund.market_data.moomoo_opend import build_moomoo_opend_market_data
from ai_henge_fund.market_data.signal_snapshot import build_signal_snapshot
from ai_henge_fund.market_data.stock_universe import get_stock_universe
from ai_henge_fund.signal_engine.deterministic import DeterministicSignalEngine
from ai_henge_fund.trading.pipeline import TradingPipeline, PipelineResult
from ai_henge_fund.tradingagents.adapter import TradingAgentsAdapter


class GraphRunner:
    def __init__(self) -> None:
        self.runtime = TradingAgentsGraphRuntime()

    def analyze(self, payload: dict) -> dict:
        decision = self.runtime.analyze(payload)
        action = decision.action.lower()
        mapped = {"buy": "BUY", "sell": "SELL", "hold": "WAIT"}.get(action, "WAIT")
        confidence = 0.0 if decision.confidence is None else decision.confidence
        result = {
            "decision": mapped,
            "confidence": confidence,
            "rationale": decision.rationale,
            "provider": decision.provider,
        }
        for key in ("quantity", "entry_price", "stop_price", "target_price", "quantity_source"):
            value = getattr(decision, key, None)
            if value is not None:
                result[key] = value
        return result

    def cancel(self, symbol: str) -> None:
        """Mark a timed-out symbol so a late graph return cannot trigger sizing."""
        self.runtime.cancel(symbol)


def _truthy(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _session_now() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def _session_open(now: datetime) -> datetime:
    return now.replace(hour=9, minute=30, second=0, microsecond=0)


def _session_close(now: datetime) -> datetime:
    return now.replace(hour=16, minute=0, second=0, microsecond=0)


def _analyze_with_timeout(pipeline: TradingPipeline, snapshot, timeout_seconds: float) -> tuple[PipelineResult | None, str | None]:
    """Run analysis in a daemon thread so a hung provider cannot block the session loop."""
    result: dict[str, PipelineResult] = {}
    error: dict[str, Exception] = {}

    def worker() -> None:
        try:
            result["value"] = pipeline.analyze(snapshot)
        except Exception as exc:
            error["value"] = exc

    started = time.monotonic()
    thread = threading.Thread(target=worker, name=f"ai-analysis-{snapshot.symbol}", daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    elapsed = time.monotonic() - started

    if thread.is_alive():
        return None, f"AI analysis timeout after {timeout_seconds:.0f}s (elapsed {elapsed:.1f}s)"
    if "value" in error:
        raise error["value"]
    if "value" not in result:
        return None, "AI analysis returned no result"
    return result["value"], None


def _cancel_timed_out_analysis(pipeline: TradingPipeline, snapshot) -> None:
    """Best-effort cancellation boundary for late provider work after a timeout."""
    adapter = getattr(pipeline, "ai_adapter", None)
    runner = getattr(adapter, "runner", None)
    cancel = getattr(runner, "cancel", None)
    if callable(cancel):
        try:
            cancel(snapshot.symbol)
        except Exception as exc:
            print(f"  AI cancellation: SKIP ({exc})")


def _send_risk_notification(pipeline: TradingPipeline, snapshot, result: PipelineResult) -> None:
    try:
        pipeline.telegram.send_risk_event(
            symbol=snapshot.symbol,
            side=result.ai_decision,
            price=float(snapshot.last_price),
            reason=result.risk.reason,
            entry_price=result.risk.entry_price,
            stop_price=result.risk.stop_price,
            target_price=result.risk.target_price,
        )
        print(f"  telegram: RISK_REJECTED sent for {snapshot.symbol}")
    except Exception as exc:
        print(f"  telegram: SKIP ({exc})")


def _send_timeout_notification(pipeline: TradingPipeline, snapshot, reason: str) -> None:
    try:
        pipeline.telegram.send_risk_event(
            symbol=snapshot.symbol,
            side="WAIT",
            price=float(snapshot.last_price),
            reason=reason,
            entry_price=None,
            stop_price=None,
            target_price=None,
        )
        print(f"  telegram: AI_TIMEOUT sent for {snapshot.symbol}")
    except Exception as exc:
        print(f"  telegram: SKIP ({exc})")


def _run_cycle(market_data, pipeline, signal_engine, universe, candle_count, interval, execute_paper, max_ai_candidates, paper_trades, max_paper_trades, scan_delay_seconds, ai_timeout_seconds, subscription_batch_size):
    """Scan the universe in quota-safe batches.

    OpenD subscriptions persist on the quote context. Each symbol needs both a
    quote and candle subscription, so a 45-symbol batch consumes at most 90 of
    the account's 100 stock-subscription slots. The context is closed and
    recreated between batches and at the start of every cycle so subscriptions
    from a previous batch/cycle cannot accumulate.
    """
    market_data.close()
    market_data = build_moomoo_opend_market_data()
    snapshots = []
    cycle_market_state = None
    total = len(universe)

    for batch_start in range(0, total, subscription_batch_size):
        batch = universe[batch_start:batch_start + subscription_batch_size]
        batch_number = batch_start // subscription_batch_size + 1
        batch_count = (total + subscription_batch_size - 1) // subscription_batch_size
        print(f"SUBSCRIPTION BATCH {batch_number}/{batch_count}: {len(batch)} symbols (quota budget <= {len(batch) * 2})")

        for offset, symbol in enumerate(batch, start=1):
            index = batch_start + offset
            try:
                quote = market_data.get_quote(symbol)
                candles = market_data.get_candles(symbol, num=candle_count, interval=interval)
                if cycle_market_state is None:
                    cycle_market_state = market_data.get_market_state(symbol)
                    print(f"CYCLE MARKET STATE: {cycle_market_state}")
                snapshot = build_signal_snapshot(symbol=symbol, quote=quote, market_state=cycle_market_state, candles=candles, data_source="moomoo_opend")
                signal = signal_engine.evaluate(snapshot)
                print(f"SCAN {symbol}: {signal.direction} score={signal.score} state={signal.setup_state}")
                if snapshot.is_usable and signal.direction in {"LONG", "SHORT"}:
                    snapshots.append((snapshot, signal))
            except Exception as exc:
                print(f"SCAN {symbol}: SKIP ({exc})")
            if index % 5 == 0 or index == total:
                print(f"SCAN HEARTBEAT: {index}/{total} symbols scanned; {len(snapshots)} candidate(s) collected")
            if scan_delay_seconds > 0:
                time.sleep(scan_delay_seconds)

        if batch_start + len(batch) < total:
            print(f"SUBSCRIPTION BATCH {batch_number}/{batch_count}: complete; resetting OpenD quote context before next batch")
            market_data.close()
            market_data = build_moomoo_opend_market_data()

    snapshots.sort(key=lambda item: abs(item[1].score), reverse=True)
    candidates = snapshots[:max_ai_candidates]
    print(f"AI analysis      : {len(candidates)} candidate(s)")

    analyzed = 0
    for candidate_index, (snapshot, _signal) in enumerate(candidates, start=1):
        analyzed += 1
        print(f"AI HEARTBEAT: {candidate_index}/{len(candidates)} starting {snapshot.symbol}")
        try:
            result, timeout_reason = _analyze_with_timeout(pipeline, snapshot, ai_timeout_seconds)
            if timeout_reason is not None:
                _cancel_timed_out_analysis(pipeline, snapshot)
                print(f"AI/PIPELINE {snapshot.symbol}: TIMEOUT ({timeout_reason})")
                _send_timeout_notification(pipeline, snapshot, timeout_reason)
                print("AI HEARTBEAT: candidate timed out; continuing with remaining candidates")
                continue
            if result is None:
                print(f"AI/PIPELINE {snapshot.symbol}: SKIP (no result)")
                continue
            if execute_paper and result.risk.action in {"BUY", "SELL"} and result.risk.quantity > 0:
                result = pipeline.execute_paper_result(snapshot, result)
        except Exception as exc:
            print(f"AI/PIPELINE {snapshot.symbol}: SKIP ({exc})")
            continue

        print(f"RESULT {snapshot.symbol}: deterministic={result.deterministic_direction} ai={result.ai_decision} risk={result.risk.action} qty={result.risk.quantity:g}")
        print(f"  reason: {result.risk.reason}")
        if result.risk.entry_price is not None:
            print(f"  entry   : ${result.risk.entry_price:,.4f}")
        if result.risk.stop_price is not None:
            print(f"  stop    : ${result.risk.stop_price:,.4f}")
        if result.risk.target_price is not None:
            print(f"  target  : ${result.risk.target_price:,.4f}")

        if result.risk.action not in {"BUY", "SELL"}:
            _send_risk_notification(pipeline, snapshot, result)

        if result.lifecycle is not None:
            paper_trades += 1
            print(f"  paper lifecycle: {result.lifecycle.action}")
            print(f"  paper message  : {result.lifecycle.reason}")
            if result.lifecycle.broker_order_id:
                print(f"  paper order ID : {result.lifecycle.broker_order_id}")
            if paper_trades >= max_paper_trades:
                break

        print(f"AI HEARTBEAT: {candidate_index}/{len(candidates)} completed {snapshot.symbol}")

    print(f"Cycle AI analyzed: {analyzed}")
    print(f"Session paper trades: {paper_trades}/{max_paper_trades}")
    return paper_trades, market_data


def main() -> int:
    candle_count = _int_env("MOOMOO_SIGNAL_CANDLES", 50)
    interval = os.getenv("MOOMOO_SIGNAL_INTERVAL", "5m").strip()
    execute_paper = _truthy("EXECUTE_PAPER")
    universe = get_stock_universe()
    max_ai_candidates = _int_env("MOOMOO_SIGNAL_MAX_AI_CANDIDATES", 5)
    max_paper_trades = _int_env("MOOMOO_SIGNAL_MAX_PAPER_TRADES", 1)
    session_loop = _truthy("SESSION_RUN_UNTIL_CLOSE", "true")
    cycle_minutes = _int_env("MOOMOO_SIGNAL_CYCLE_MINUTES", 20)
    scan_delay_seconds = _float_env("MOOMOO_SIGNAL_SCAN_DELAY_SECONDS", 3.2)
    ai_timeout_seconds = _float_env("MOOMOO_SIGNAL_AI_TIMEOUT_SECONDS", 90.0)
    subscription_batch_size = min(_int_env("MOOMOO_SIGNAL_SUBSCRIPTION_BATCH_SIZE", 45), 50)

    print("=" * 72)
    print("AI Henge Fund - Moomoo OpenD Universe Signal Pipeline")
    print("=" * 72)
    print(f"Universe        : {len(universe)} symbols")
    print(f"Candles         : {candle_count} x {interval}")
    print(f"AI candidates   : max {max_ai_candidates} per cycle")
    print(f"Paper trades    : max {max_paper_trades} per session")
    print(f"Session mode    : {'UNTIL U.S. CLOSE' if session_loop else 'SINGLE CYCLE'}")
    print(f"Cycle interval  : {cycle_minutes} minutes")
    print(f"Scan throttle   : {scan_delay_seconds:.1f}s between symbols")
    print(f"AI timeout      : {ai_timeout_seconds:.0f}s per candidate")
    print(f"Subscription batches: max {subscription_batch_size} symbols ({subscription_batch_size * 2} stock subscriptions/batch)")
    print(f"Paper execution : {'ENABLED' if execute_paper else 'DISABLED (analysis only)'}")
    print("Live trading    : DISABLED")

    market_data = build_moomoo_opend_market_data()
    if not market_data.enabled:
        print("FAIL: MOOMOO_OPEND_ENABLED=true and MOOMOO_READ_ONLY=true are required.")
        return 2

    pipeline = TradingPipeline(ai_adapter=TradingAgentsAdapter(GraphRunner()))
    signal_engine = DeterministicSignalEngine()
    paper_trades = 0
    session_resumed = False
    try:
        while True:
            now = _session_now()
            if not session_loop:
                pipeline.resume_paper_session()
                paper_trades, market_data = _run_cycle(market_data, pipeline, signal_engine, universe, candle_count, interval, execute_paper, max_ai_candidates, paper_trades, max_paper_trades, scan_delay_seconds, ai_timeout_seconds, subscription_batch_size)
                pipeline.handoff_paper_session()
                break
            if now.weekday() >= 5:
                print(f"U.S. market is closed today ({now:%A}). Exiting cleanly.")
                break
            if now < _session_open(now):
                wait_seconds = max(1, int((_session_open(now) - now).total_seconds()))
                print(f"Waiting for U.S. regular open at 09:30 ET ({wait_seconds}s).")
                time.sleep(min(wait_seconds, 300))
                continue
            if now >= _session_close(now):
                pipeline.handoff_paper_session()
                print("U.S. regular session closed at 16:00 ET. Overnight handoff completed.")
                break

            if not session_resumed:
                pipeline.resume_paper_session()
                session_resumed = True

            print(f"\nSESSION CYCLE {now:%Y-%m-%d %H:%M:%S %Z}")
            if paper_trades >= max_paper_trades:
                print("Paper-trade session limit reached; continuing market monitoring without new orders.")
            else:
                paper_trades, market_data = _run_cycle(market_data, pipeline, signal_engine, universe, candle_count, interval, execute_paper, max_ai_candidates, paper_trades, max_paper_trades, scan_delay_seconds, ai_timeout_seconds, subscription_batch_size)
            now = _session_now()
            if now >= _session_close(now):
                pipeline.handoff_paper_session()
                print("U.S. regular session closed. Overnight handoff completed.")
                break
            sleep_seconds = min(cycle_minutes * 60, max(1, int((_session_close(now) - now).total_seconds())))
            print(f"Next scan in {sleep_seconds // 60} minute(s).")
            time.sleep(sleep_seconds)
        print(f"Universe scanned per cycle: {len(universe)}")
        print(f"Session paper trades: {paper_trades}")
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
