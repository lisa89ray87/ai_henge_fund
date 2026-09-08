from .engine import PaperTrade, PaperTradingEngine
from .service import PaperTradeService

# Install the Moomoo paper-entry lifecycle guard at package load time. This keeps
# WORKING entry orders reserved and monitored without changing live trading.
from . import pending_entry_guard as _pending_entry_guard

try:
    from .moomoo_lifecycle import MoomooPaperTradeLifecycle
    _pending_entry_guard.install(MoomooPaperTradeLifecycle)
except ImportError:
    # Keep lightweight paper-trading imports usable when the optional Moomoo
    # dependency is unavailable (for example in unrelated unit tests).
    pass

__all__ = ["PaperTrade", "PaperTradingEngine", "PaperTradeService"]
