from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ai_henge_fund.config.settings import get_settings
from ai_henge_fund.market_data.signal_snapshot import SignalSnapshot
from ai_henge_fund.signal_engine.deterministic import DeterministicSignal
from ai_henge_fund.tradingagents.adapter import AITradeDecision


@dataclass(frozen=True)
class RiskDecision:
    action: str
    quantity: float
    risk_per_share: float | None
    reason: str
    checks: tuple[str, ...]
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None


class RiskGate:
    """Gate between AI analysis and execution.

    Paper/SIMULATE mode validates trade structure and AI sizing but deliberately
    ignores live capital-budget constraints. Live mode enforces the configured
    capital, per-trade risk, daily-loss, and position limits.
    """

    def __init__(
        self,
        *,
        max_position_value: float | None = None,
        min_ai_confidence: float = 0.70,
        allowed_market_states: Iterable[str] = ("REGULAR", "PRE_MARKET", "AFTERNOON", "AFTER_HOURS"),
        reward_risk_multiple: float | None = None,
    ) -> None:
        settings = get_settings()
        if max_position_value is None:
            max_position_value = settings.ai_henge_fund_max_capital_deployed
        if max_position_value <= 0:
            raise ValueError("max_position_value must be greater than zero")
        if not 0 <= min_ai_confidence <= 1:
            raise ValueError("min_ai_confidence must be between 0 and 1")
        if reward_risk_multiple is None:
            reward_risk_multiple = settings.ai_henge_fund_min_reward_risk
        if reward_risk_multiple <= 0:
            raise ValueError("reward_risk_multiple must be greater than zero")
        self.max_position_value = min(max_position_value, settings.ai_henge_fund_max_capital_deployed)
        self.starting_capital = settings.ai_henge_fund_starting_capital
        self.risk_per_trade_pct = settings.ai_henge_fund_risk_per_trade_pct
        self.max_daily_loss = settings.ai_henge_fund_max_daily_loss
        self.max_positions = settings.ai_henge_fund_max_positions
        self.risk_profile = settings.ai_henge_fund_risk_profile
        self.paper_mode = bool(settings.moomoo_paper_trading_enabled and not settings.moomoo_live_trading_enabled)
        self.min_ai_confidence = 0.65 if self.risk_profile == "aggressive_paper" and self.paper_mode else min_ai_confidence
        self.allowed_market_states = frozenset(allowed_market_states)
        self.reward_risk_multiple = reward_risk_multiple
        self.paper_mode = bool(settings.moomoo_paper_trading_enabled and not settings.moomoo_live_trading_enabled)

    @staticmethod
    def _trade_levels(snapshot: SignalSnapshot, direction: str) -> tuple[float, float, float]:
        """Build deterministic levels when AI/fallback did not provide them."""
        entry = float(snapshot.last_price)
        candles = snapshot.candles[-5:]
        lows = [float(c["low"]) for c in candles if c.get("low") is not None]
        highs = [float(c["high"]) for c in candles if c.get("high") is not None]
        if direction == "BUY":
            if not lows:
                raise ValueError("Recent low data unavailable for LONG stop")
            stop = min(lows)
            if stop >= entry:
                raise ValueError("LONG stop is not below entry")
            target = entry + (entry - stop) * 2.0
        else:
            if not highs:
                raise ValueError("Recent high data unavailable for SHORT stop")
            stop = max(highs)
            if stop <= entry:
                raise ValueError("SHORT stop is not above entry")
            target = entry - (stop - entry) * 2.0
        return entry, stop, target

    @staticmethod
    def _validate_ai_levels(ai: AITradeDecision, expected: str) -> tuple[float, float, float] | None:
        if ai.entry_price is None or ai.stop_price is None or ai.target_price is None:
            return None
        entry = float(ai.entry_price)
        stop = float(ai.stop_price)
        target = float(ai.target_price)
        if min(entry, stop, target) <= 0:
            raise ValueError("AI returned a non-positive trade level")
        if expected == "BUY" and not (stop < entry < target):
            raise ValueError("AI LONG levels must satisfy stop < entry < target")
        if expected == "SELL" and not (target < entry < stop):
            raise ValueError("AI SHORT levels must satisfy target < entry < stop")
        return entry, stop, target

    def evaluate(
        self,
        snapshot: SignalSnapshot,
        signal: DeterministicSignal,
        ai: AITradeDecision,
        *,
        deployed_capital: float = 0.0,
        daily_realized_loss: float = 0.0,
        open_position_count: int = 0,
    ) -> RiskDecision:
        checks: list[str] = []
        if self.risk_profile == "aggressive_paper" and self.paper_mode:
            checks.append("RISK_PROFILE_AGGRESSIVE_PAPER")

        if not snapshot.is_usable:
            return RiskDecision("WAIT", 0, None, "Market snapshot is not usable", tuple(checks))
        checks.append("DATA_USABLE")

        if snapshot.data_quality not in {"LIVE", "VERIFIED"}:
            return RiskDecision("WAIT", 0, None, "Market data quality is insufficient", tuple(checks))
        checks.append("DATA_QUALITY")

        if snapshot.market_state not in self.allowed_market_states:
            return RiskDecision("WAIT", 0, None, f"Market state {snapshot.market_state!r} is not tradable", tuple(checks))
        checks.append("MARKET_STATE")

        if signal.setup_state != "CANDIDATE":
            return RiskDecision("WAIT", 0, None, "Deterministic setup is not a trade candidate", tuple(checks))
        checks.append("DETERMINISTIC_SETUP")

        expected = "BUY" if signal.direction == "LONG" else "SELL" if signal.direction == "SHORT" else "WAIT"
        regime = str(snapshot.metadata.get("market_regime", "UNKNOWN")).upper()
        if regime == "UNKNOWN":
            # Missing broad-market regime is degraded data, not proof that the
            # individual setup is unsafe. Continue evaluating the candidate,
            # while making the degraded condition observable for analysis.
            checks.append("MARKET_REGIME_UNKNOWN")
        if regime == "RISK_OFF" and expected == "BUY":
            return RiskDecision("WAIT", 0, None, "RISK_OFF regime blocks new LONG entries", tuple(checks + ["MARKET_REGIME"]))
        if regime == "RISK_ON" and expected == "SELL":
            return RiskDecision("WAIT", 0, None, "RISK_ON regime blocks new SHORT entries", tuple(checks + ["MARKET_REGIME"]))
        checks.append("MARKET_REGIME_" + regime)
        if ai.decision != expected:
            return RiskDecision("WAIT", 0, None, "AI decision does not confirm deterministic direction", tuple(checks))
        checks.append("AI_DIRECTION")

        if ai.confidence < self.min_ai_confidence:
            return RiskDecision("WAIT", 0, None, "AI confidence below risk threshold", tuple(checks))
        checks.append("AI_CONFIDENCE")

        if self.max_positions > 0 and open_position_count >= self.max_positions:
            return RiskDecision("WAIT", 0, None, "Maximum simultaneous position limit reached", tuple(checks))
        checks.append("POSITION_COUNT")

        try:
            ai_levels = self._validate_ai_levels(ai, expected)
        except ValueError as exc:
            return RiskDecision("WAIT", 0, None, str(exc), tuple(checks))

        if ai_levels is not None:
            entry, stop, target = ai_levels
            checks.append("AI_TRADE_LEVELS")
        else:
            try:
                entry, stop, target = self._trade_levels(snapshot, expected)
            except ValueError as exc:
                return RiskDecision("WAIT", 0, None, str(exc), tuple(checks))
            checks.append("TRADE_LEVELS_FALLBACK")

        risk_per_share = abs(entry - stop)
        if risk_per_share <= 0:
            return RiskDecision("WAIT", 0, None, "Invalid trade risk distance", tuple(checks))

        # Reject stops that sit inside recent structure. A small ATR buffer
        # avoids treating a single candle wick as a sufficient invalidation level.
        candle_ohlc = [c for c in snapshot.candles[-14:] if c.get("high") is not None and c.get("low") is not None]
        if candle_ohlc:
            try:
                atr = sum(float(c["high"]) - float(c["low"]) for c in candle_ohlc) / len(candle_ohlc)
                recent_ohlc = [c for c in snapshot.candles[-5:] if c.get("high") is not None and c.get("low") is not None]
                if recent_ohlc and atr > 0:
                    if expected == "BUY":
                        swing_low = min(float(c["low"]) for c in recent_ohlc)
                        buffer_multiple = 0.05 if self.risk_profile == "aggressive_paper" and self.paper_mode else 0.10
                        structural_limit = min(swing_low, entry - (atr * buffer_multiple))
                        if stop > structural_limit:
                            return RiskDecision("WAIT", 0, risk_per_share,
                                f"LONG stop ${stop:.4f} is inside recent structure/ATR buffer ${structural_limit:.4f}",
                                tuple(checks + ["STRUCTURAL_STOP_REJECT"]),
                                entry_price=entry, stop_price=stop, target_price=target)
                    else:
                        swing_high = max(float(c["high"]) for c in recent_ohlc)
                        buffer_multiple = 0.05 if self.risk_profile == "aggressive_paper" and self.paper_mode else 0.10
                        structural_limit = max(swing_high, entry + (atr * buffer_multiple))
                        if stop < structural_limit:
                            return RiskDecision("WAIT", 0, risk_per_share,
                                f"SHORT stop ${stop:.4f} is inside recent structure/ATR buffer ${structural_limit:.4f}",
                                tuple(checks + ["STRUCTURAL_STOP_REJECT"]),
                                entry_price=entry, stop_price=stop, target_price=target)
                    checks.append("STRUCTURAL_STOP")
            except (TypeError, ValueError):
                checks.append("STRUCTURAL_STOP_SKIPPED")

        reward_per_share = abs(target - entry)
        reward_risk = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
        effective_reward_risk = self.reward_risk_multiple
        if self.risk_profile == "aggressive_paper" and self.paper_mode:
            favorable_regime = (regime == "RISK_ON" and expected == "BUY") or (regime == "RISK_OFF" and expected == "SELL")
            if abs(signal.score) >= 7 and favorable_regime:
                effective_reward_risk = 1.75
                checks.append("ADAPTIVE_REWARD_RISK_1_75")
        if reward_risk < effective_reward_risk:
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                f"Reward/risk {reward_risk:.2f} is below minimum {effective_reward_risk:.2f}",
                tuple(checks + ["REWARD_RISK_REJECT"]), entry_price=entry, stop_price=stop, target_price=target,
            )
        checks.append("REWARD_RISK")

        # AI sizing is authoritative in both paper and live modes. A missing,
        # non-integral, or non-positive AI quantity is never silently replaced.
        if ai.quantity is None:
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                "AI did not provide a valid position size",
                tuple(checks), entry_price=entry, stop_price=stop, target_price=target,
            )
        raw_quantity = float(ai.quantity)
        if raw_quantity <= 0 or not raw_quantity.is_integer():
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                "AI did not provide a valid whole-share position size",
                tuple(checks), entry_price=entry, stop_price=stop, target_price=target,
            )
        ai_quantity = int(raw_quantity)
        checks.append("AI_POSITION_SIZE")

        if self.paper_mode:
            # Simulation is for strategy/execution testing. Do not constrain it
            # using the future live account's $100/$90/$10 capital budgets.
            checks.append("PAPER_CAPITAL_LIMITS_BYPASSED")
            return RiskDecision(
                expected,
                float(ai_quantity),
                risk_per_share,
                "Paper trade accepted using AI position size; live capital limits bypassed",
                tuple(checks),
                entry_price=entry, stop_price=stop, target_price=target,
            )

        # Live-only capital/risk controls.
        if daily_realized_loss >= self.max_daily_loss:
            return RiskDecision("WAIT", 0, None, "Maximum daily loss limit reached", tuple(checks))
        checks.append("DAILY_LOSS")

        available_deployment = self.max_position_value - max(0.0, deployed_capital)
        if available_deployment <= 0:
            return RiskDecision("WAIT", 0, None, "Maximum deployed capital reached", tuple(checks))
        checks.append("DEPLOYED_CAPITAL")

        configured_trade_risk = self.starting_capital * self.risk_per_trade_pct / 100.0
        remaining_daily_loss = max(0.0, self.max_daily_loss - max(0.0, daily_realized_loss))
        allowed_trade_risk = min(configured_trade_risk, remaining_daily_loss)
        if allowed_trade_risk <= 0:
            return RiskDecision("WAIT", 0, None, "No daily risk budget remains", tuple(checks))

        capital_required = ai_quantity * entry
        risk_required = ai_quantity * risk_per_share
        if capital_required > available_deployment:
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                "AI position size exceeds live capital limit", tuple(checks),
                entry_price=entry, stop_price=stop, target_price=target,
            )
        if risk_required > allowed_trade_risk:
            return RiskDecision(
                "WAIT", 0, risk_per_share,
                "AI position size exceeds live risk limit", tuple(checks),
                entry_price=entry, stop_price=stop, target_price=target,
            )
        checks.append("LIVE_CAPITAL_LIMIT")
        checks.append("LIVE_RISK_LIMIT")

        return RiskDecision(
            expected,
            float(ai_quantity),
            risk_per_share,
            "All live risk gates passed using AI position size",
            tuple(checks),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
        )
