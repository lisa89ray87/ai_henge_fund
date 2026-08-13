# AI Henge Fund — Stable Integration Contract

## Purpose

This document is the implementation contract for future models/agents working on this repository. Preserve these boundaries unless a deliberate architecture change is approved.

## Source of truth

`daily_stock_analyse` remains authoritative for its existing live stock alerts, catalyst/news processing, market-trend/regime analysis, scoring, and signal lifecycle. AI Henge Fund consumes those signals; it does not rebuild those engines.

## Provider boundaries

- `daily_stock_analyse` → persisted signal source.
- `TradingAgents` → independent reasoning layer above the imported signal.
- `Moomoo MCP` → live quote/market-data and, later, broker capability. Start read-only/paper.
- `ai_henge_fund` → normalization, decision context, risk controls, portfolio state, and orchestration.
- Telegram/email → presentation/notification only.

## Canonical flow

`daily_stock_analyse → ai_signals → DecisionContext → TradingAgents + Moomoo → risk engine → alert`

## Non-negotiable rules

1. Do not rename, delete, or repurpose `daily_stock_analyse` source tables.
2. Do not duplicate the live-alert, catalyst, or market-regime engines in AI Henge Fund.
3. Do not let an MCP-specific payload shape leak into the decision layer. Normalize it first.
4. Do not enable live order execution while the read-only data and decision path is still being validated.
5. Keep provider adapters optional so tests do not require a live Moomoo MCP session.
6. Preserve signal provenance using `source` and `source_signal_id`.
7. Prefer small, targeted tests over repeated full integration runs when no relevant code changed.

## Current milestone

The signal sync is operational. The next implementation boundary is live quote enrichment through the Moomoo MCP adapter, followed by real TradingAgents reasoning. Neither should alter the existing signal engine.
