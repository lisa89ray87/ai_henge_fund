"""Run the real TradingAgents reasoning boundary over imported signals."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_henge_fund.agents.tradingagents_bridge import (
    TradingAgentsBridge,
    TradingAgentsGraphRuntime,
)
from ai_henge_fund.database.models import AgentRun, AgentRunStatus, Signal
from ai_henge_fund.database.session import session_scope


def main() -> int:
    # This is deliberately the real TradingAgents graph, not the development
    # passthrough. TradingAgents remains analysis-only; no broker/order API is
    # called by this workflow.
    bridge = TradingAgentsBridge(TradingAgentsGraphRuntime())
    processed = 0

    with session_scope() as session:
        signals = (
            session.query(Signal)
            .order_by(Signal.generated_at.desc())
            .limit(20)
            .all()
        )

        if not signals:
            print("No imported signals are available for TradingAgents reasoning.")
            print("TradingAgents reasoning stage: PASS (nothing to process)")
            return 0

        for signal in signals:
            started = datetime.now(timezone.utc)
            agent_run = AgentRun(
                strategy_id=signal.strategy_id,
                agent_name="tradingagents_signal_review",
                symbol=signal.symbol,
                status=AgentRunStatus.RUNNING,
                started_at=started,
                input_summary=bridge.build_request(signal)["reasoning"],
            )
            session.add(agent_run)
            session.flush()

            try:
                decision = bridge.analyze(signal)
                agent_run.status = AgentRunStatus.COMPLETED
                agent_run.completed_at = datetime.now(timezone.utc)
                agent_run.output_summary = (
                    f"action={decision.action}; confidence={decision.confidence}; "
                    f"provider={decision.provider}; rationale={decision.rationale}"
                )
                processed += 1
                print(
                    f"TradingAgents analyzed {signal.symbol}: "
                    f"action={decision.action}, confidence={decision.confidence}"
                )
            except Exception as exc:
                agent_run.status = AgentRunStatus.FAILED
                agent_run.completed_at = datetime.now(timezone.utc)
                agent_run.error_message = str(exc)
                raise

    print(f"Imported signals processed by real TradingAgents: {processed}")
    print("TradingAgents reasoning stage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
