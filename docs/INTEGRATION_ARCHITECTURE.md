# AI Henge Fund Integration Architecture

## Principle

`daily_stock_analyse` remains the source of truth for its existing live stock alerts, live event alerts, catalyst/news processing, market-regime engine, deterministic scoring, Telegram/email reporting, and signal lifecycle.

AI Henge Fund consumes the persisted signal output instead of copying or rewriting those engines.

## Data flow

```text
 daily_stock_analyse
       |
       | PostgreSQL signals / analysis_runs
       v
 AI Henge Fund read-only adapter
       |
       v
 ai_signals
       |
       +--> TradingAgents reasoning
       |
       +--> Risk engine
       |
       +--> Portfolio / orders / executions
       |
       v
 Moomoo MCP (later, paper/read-only first)
```

## Why `ai_signals` is separate

The existing `daily_stock_analyse` repository already owns a PostgreSQL table named `signals`. AI Henge Fund therefore uses `ai_signals` for its normalized internal signal domain. This prevents schema collisions and allows the existing engine to keep running unchanged.

Each imported signal records:

- `source = daily_stock_analyse`
- `source_signal_id = <legacy signal_id>`
- normalized action (`LONG -> BUY`, `SHORT -> SELL`)
- normalized confidence
- target price
- catalyst and market-regime context in reasoning

The adapter is read-only against the source tables. It never updates or deletes `daily_stock_analyse` records.

## Database

Both repositories may use the same Neon PostgreSQL database. They own different tables:

- `daily_stock_analyse`: `analysis_runs`, `signals`, `signal_outcomes`, `schema_migrations`
- `ai_henge_fund`: `portfolios`, `positions`, `orders`, `executions`, `strategies`, `ai_signals`, `agent_runs`

Do not rename or remove the existing `daily_stock_analyse` tables.

## Next milestones

1. Verify the existing Neon secret works from GitHub Actions.
2. Run the AI Henge Fund Alembic migration without touching the existing daily-stock tables.
3. Add a scheduled/manual signal-sync job.
4. Add TradingAgents as a second reasoning layer above imported signals.
5. Add Moomoo MCP as a market-data/broker adapter, initially read-only/simulated.
6. Add the risk engine before any live order capability.
