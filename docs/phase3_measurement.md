# Phase 3 — Measurement and Memory

## 1. Goal

Know exactly what the system decided and why.

## 2. Scope

Phase 3 ensures that every trade and no-trade decision is persisted with full
context, queryable after the fact, and explainable through API/dashboard without
relying on terminal logs.

## 3. Decision Journal Schema

All decisions are stored in `paper_trades.db` → `paper_decisions` table:

| Column | Type | Purpose |
|---|---|---|
| `timestamp` | REAL | UNIX epoch of decision |
| `session_id` | TEXT | Unique session identifier for cross-session comparison |
| `wallet_id` | TEXT | Which wallet triggered the decision |
| `cycle_phase` | TEXT | Pipeline stage (task_factory, paper_engine, etc.) |
| `action` | TEXT | BUY, SELL, HOLD, WARMUP, RISK_BLOCKED, etc. |
| `regime_label` | TEXT | Market regime at decision time (LOW_VOL, HIGH_VOL, etc.) |
| `setup_tag` | TEXT | Strategy setup detected (momentum_long, exit_long, signal_wait, etc.) |
| `decision_class` | TEXT | Clean category: EXECUTED, ERROR, WARMUP, BLOCKED, SKIPPED |
| `primary_reason` | TEXT | Human-readable skip/block reason |
| `reason_codes` | TEXT (JSON) | Machine-parseable reason codes tuple |
| `raw_alpha` | REAL | Raw alpha signal strength |
| `robust_alpha` | REAL | Robust (fractional diff + ADF) alpha signal |
| `confidence` | REAL | ML model confidence [0, 1] |
| `adf_pvalue` | REAL | ADF stationarity test p-value |
| `stationarity_d` | REAL | Fractional differentiation order |
| `volatility_regime` | TEXT | Volatility regime label |
| `risk_position_usd` | REAL | Risk committee approved position size |
| `trade_budget_usd` | REAL | Final trade budget after all filters |
| `gas_cost_usd` | REAL | Estimated gas cost |
| `total_equity_usd` | REAL | Total portfolio equity at decision |
| `pnl_usd` | REAL | Realized PnL (for trades) |
| `notes` | TEXT | Free-form context notes |

### Indices

- `idx_pd_ts` — timestamp (time-range queries)
- `idx_pd_session` — session_id (cross-session comparison)
- `idx_pd_action` — action (filter by trade/skip)
- `idx_pd_reason` — primary_reason (skip reason analysis)
- `idx_pd_regime` — regime_label (regime performance)
- `idx_pd_setup` — setup_tag (setup performance)

## 4. Decision Classification

Clean, non-overlapping `decision_class` categories:

| Class | Actions | Meaning |
|---|---|---|
| `EXECUTED` | BUY, SELL | A real trade was placed |
| `ERROR` | PRICE_ERROR, INVALID_PRICE, WRONG_CHAIN, FLASH_CRASH | Hard failure |
| `WARMUP` | WARMUP | Insufficient data (transient, resolves after startup) |
| `BLOCKED` | HALTED, RISK_BLOCKED | Safety override or risk committee block |
| `SKIPPED` | HOLD, and all other actions | No valid signal found |

## 5. API Endpoints

### `/api/decisions` — Decision Journal Query

**Query Parameters:**

| Param | Default | Purpose |
|---|---|---|
| `session_id` | (none) | Filter by specific session |
| `limit` | 100 | Max rows to return |
| `format` | json | `json` or `csv` |

**Responses:**

- **No session_id (default):** Returns session summary + recent decisions
  ```json
  {
    "status": "ok",
    "sessions": [{"session_id": "...", "total_decisions": N, "executed": N, "skipped": N, ...}],
    "recent_decisions": [...]
  }
  ```

- **With session_id:** Returns all decisions from that session
  ```json
  {
    "status": "ok",
    "session_id": "...",
    "count": N,
    "decisions": [...]
  }
  ```

- **format=csv:** Returns CSV download of all decisions (or filtered by session)

### `/api/paper_health` — Skip Reason Distribution

Returns decision throughput metrics, skip reason distribution, and sample
starvation diagnosis. Used for Phase 2 monitoring.

### `/api/research` — Full Research Snapshot

Returns trades, decisions, analytics, regime breakdown, setup breakdown,
advanced analytics (expectancy, payoff ratio, profit factor), and live
readiness gates.

### `/api/runtime` — Full Runtime State

Returns execution mode, live guard status, portfolio state, audit sessions,
and research summary.

## 6. Dashboard Integration

The dashboard at `/dashboard` renders:

- **No-Trade Reasons table** — top skip reasons with counts
- **Decision Journal table** — recent decisions with time, action, reason, regime, setup
- **Regime Performance table** — per-regime: decisions, closed, win%, expectancy, PnL
- **Setup Performance table** — per-setup: same metrics
- **Recent Audit Sessions table** — session history with paper trade counts

## 7. Session Tracking

Each bot start generates a unique `session_id` (format: `session_<unix_timestamp>`).

All decisions are tagged with `session_id`, enabling:
- Cross-session performance comparison
- Isolating behavior changes between sessions
- Filtering decisions by specific runtime windows

## 8. Migration

### Phase 3 Migration (2026-04-06)

Added `session_id` column to existing `paper_decisions` tables:

```sql
ALTER TABLE paper_decisions ADD COLUMN session_id TEXT NOT NULL DEFAULT 'unknown'
CREATE INDEX IF NOT EXISTS idx_pd_session ON paper_decisions(session_id)
```

Migration runs automatically on VirtualLedger initialization. Existing
decisions retain `session_id = 'unknown'`.

## 9. Exit Gate Assessment

Phase 3 exit gate (roadmap §9.7):

> Operators can answer "what happened and why" without relying on terminal logs.

| Requirement | Status |
|---|---|
| Decision journal integrity | ✅ DONE — 22-column schema with full context |
| No-trade persistence | ✅ DONE — all skips/blocks persisted with reasons |
| Regime/setup tagging | ✅ DONE — regime_label + setup_tag on every decision |
| Audit snapshots | ✅ DONE — paper_snapshots + paper_balance_history + analytics sessions |
| Runtime summaries | ✅ DONE — /api/runtime, /api/research, /api/paper_health |
| Research summaries | ✅ DONE — full analytics with expectancy, win rate, regime/setup breakdown |
| Dashboard shows skip reasons | ✅ DONE — No-Trade Reasons table + Decision Journal table |
| Queryable "why skipped?" (not logs) | ✅ DONE — /api/decisions with filtering + CSV export |
| Cross-session comparison | ✅ DONE — session_id column + /api/decisions?session_id= |
| Clean decision classification | ✅ DONE — EXECUTED/ERROR/WARMUP/BLOCKED/SKIPPED (no overlap) |

**Phase 3 is COMPLETE.**

## 10. Files Modified

- `wallet_manager/strategies/paper_engine.py`
  - Added `session_id` to VirtualLedger `__init__` and `paper_decisions` schema
  - Added migration logic for session_id column
  - Added `get_decisions_by_session()` method
  - Added `export_decisions_csv()` method
  - Updated `get_recent_decisions()` to include session_id
  - Fixed `_classify_decision_class()` — clean non-overlapping categories

- `wallet_manager/metrics_server.py`
  - Added `/api/decisions` endpoint with session_id filtering and CSV export

## 11. After-State

Operators can now:
1. Query `/api/decisions` to see all decisions with full context
2. Filter by `session_id` to isolate specific runtime windows
3. Download CSV for offline analysis
4. See skip reasons on dashboard without checking logs
5. Compare performance across sessions
6. Answer "what happened and why" through persisted data, not terminal output
