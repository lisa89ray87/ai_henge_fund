"""Adapters for integrating existing external trading systems."""

from ai_henge_fund.database.integrations.daily_stock_analyse import (
    DAILY_STOCK_ANALYSE_SOURCE,
    sync_daily_stock_signals,
)

__all__ = ["DAILY_STOCK_ANALYSE_SOURCE", "sync_daily_stock_signals"]
