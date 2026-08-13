# AI Henge Fund

Production-style AI trading research and portfolio infrastructure.

## Current architecture

AI Henge Fund deliberately reuses the existing `daily_stock_analyse` engine rather than rebuilding its proven live-alert, catalyst/news, market-regime, scoring, reporting, and signal-lifecycle components.

See [`docs/INTEGRATION_ARCHITECTURE.md`](docs/INTEGRATION_ARCHITECTURE.md) for the integration boundary.

### Components

- **daily_stock_analyse** — existing deterministic market/news/catalyst/live-alert engine
- **TradingAgents** — planned higher-level multi-agent research and reasoning layer
- **Moomoo MCP** — planned market-data and broker adapter; read-only/simulated first
- **Neon PostgreSQL** — shared persistence layer with separate table ownership
- **AI Henge Fund** — portfolio, risk, normalized signals, orders, executions, and orchestration

No live trading is enabled by this repository at the current stage.
