# Phase 7 — Risk Operating System

## 1. Goal

Make risk a first-class operating layer that can be reasoned about as
a system, not as scattered conditionals across multiple modules.

## 2. Before-State Gap

| Component | Pre-Phase-7 State |
|---|---|
| `risk_committee.py` | 8 brakes, committee verdict, `to_dict()` — isolated |
| `risk_intelligence.py` | DrawdownAccel, FatTailVaR, StressEngine, RegimeLimits — isolated |
| `deep_kelly_risk.py` | Drawdown state, VaR, Kelly — isolated |
| Risk state persistence | None |
| Composite risk level | None |
| Audit trail | None |
| Unified API surface | `/api/risk` (committee only) + `/api/risk_intelligence` (intelligence only) |

No single model unified these components. Risk decisions were not
persisted. Answering "what was the risk state at decision time?" was not
possible from data alone.

## 3. New Module: `wallet_manager/risk_os.py`

### 3.1 RiskLevel

```
GREEN  — No active brakes; composite score < 30
YELLOW — REDUCE verdicts or composite score 30-59
ORANGE — ≥2 REDUCE verdicts or composite score 60-79
RED    — At least 1 BLOCK brake active
```

### 3.2 Composite Score (0-100)

| Source | Contribution |
|---|---|
| Each blocking brake | +25 (capped at 75) |
| Each reducing brake | +10 (capped at 30) |
| Drawdown 5-10% | +15 |
| Drawdown > 10% | +25 |
| VaR99 > 2% | +10 |
| Total | min(100, sum) |

### 3.3 RiskStateSnapshot

All risk evaluation results in one frozen dataclass:

| Field | Type | Source |
|---|---|---|
| `snapshot_id` | str (uuid4) | generated |
| `session_id` | str | paper engine ledger |
| `timestamp` | float | time.time() |
| `risk_level` | RiskLevel | classification |
| `composite_score` | int (0-100) | formula above |
| `committee_verdict` | dict | `CommitteeVerdict.to_dict()` |
| `blocking_brakes` | list[str] | `CommitteeVerdict.blocking_brakes` |
| `reducing_brakes` | list[str] | derived from brake_results |
| `drawdown_pct` | float | max(RiskIntelligence, DeepKelly) |
| `drawdown_state` | str | DeepKelly drawdown state |
| `var_99_pct` | float | FatTailVaR report |
| `regime_label` | str | caller-provided |
| `kelly_multiplier` | float | `RiskIntelligence.get_effective_kelly_multiplier()` |
| `veto_narrative` | str | structured explanation |

### 3.4 RiskStateStore

Persists to `quant_analytics.db` → `risk_state_snapshots` table.

Table schema:

```sql
CREATE TABLE risk_state_snapshots (
    snapshot_id      TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL DEFAULT 'unknown',
    timestamp        REAL NOT NULL,
    risk_level       TEXT NOT NULL,
    composite_score  INTEGER NOT NULL,
    blocking_brakes  TEXT NOT NULL,
    reducing_brakes  TEXT NOT NULL,
    drawdown_pct     REAL NOT NULL DEFAULT 0.0,
    drawdown_state   TEXT NOT NULL DEFAULT 'normal',
    var_99_pct       REAL NOT NULL DEFAULT 0.0,
    regime_label     TEXT NOT NULL DEFAULT 'unknown',
    kelly_multiplier REAL NOT NULL DEFAULT 1.0,
    veto_narrative   TEXT NOT NULL DEFAULT '',
    payload_json     TEXT NOT NULL DEFAULT '{}'
)
```

Indices: `idx_rss_timestamp` (timestamp DESC), `idx_rss_session`

Methods:
- `record(snapshot)` — INSERT OR IGNORE (idempotent)
- `get_recent(limit=20)` — newest first
- `get_risk_trajectory(hours=24)` — (timestamp, risk_level, composite_score) series
- `count()` — total record count

### 3.5 RiskOS Facade

```python
ros = get_risk_os()
snapshot = await ros.evaluate_and_record(
    paper_engine=engine,
    confidence=0.65,
    regime_label="low_vol",
    equity_usd=10_500.0,
    session_id="session_1234567890",
)
# snapshot.risk_level == RiskLevel.GREEN
# snapshot.veto_narrative == "[GREEN] composite=0/100 | dd=0.0% | var99=0.00% | ..."
```

## 4. API Endpoint

### `/api/risk_state` — Phase 7 Primary Risk Surface

Returns:

```json
{
  "status": "ok",
  "generated_at": 1744100000.0,
  "risk_state": {
    "snapshot_id": "...",
    "risk_level": "GREEN",
    "composite_score": 5,
    "blocking_brakes": [],
    "reducing_brakes": [],
    "drawdown_pct": 0.0,
    "drawdown_state": "normal",
    "var_99_pct": 0.005,
    "regime_label": "low_vol",
    "kelly_multiplier": 1.0,
    "veto_narrative": "[GREEN] composite=5/100 | all_clear | ...",
    "committee_verdict": { ... }
  },
  "recent_snapshots": [ ... ],
  "trajectory_24h": [ ... ],
  "total_snapshots": 142
}
```

## 5. Telegram Command

```
/risk_state
```

Returns current risk level icon (🟢🟡🟠🔴), composite score, drawdown,
VaR-99, regime, Kelly multiplier, and brake status.

## 6. Files Modified

- `wallet_manager/risk_os.py` — new module (Phase 7 core)
- `wallet_manager/metrics_server.py` — added `_handle_risk_state_api`, route `/api/risk_state`
- `wallet_manager/security/telegram_commands.py` — added `_CMD_RISK_STATE`, `_handle_risk_state`, dispatch, help entry
- `tests/unit/test_phase7_risk_os.py` — new test file
- `docs/phase7_risk_os.md` — this file

## 7. Unchanged Files

- `wallet_manager/risk_committee.py` — brakes untouched
- `wallet_manager/risk_intelligence.py` — untouched
- `wallet_manager/strategies/deep_kelly_risk.py` — untouched
- `wallet_manager/strategies/paper_engine.py` — untouched

## 8. Exit Gate Assessment

| Requirement | Status |
|---|---|
| `RiskStateSnapshot` unifies committee + intelligence into one model | ✅ DONE |
| `RiskStateStore` persists and queries snapshots (DB audit trail) | ✅ DONE |
| `/api/risk_state` returns full system risk picture in one call | ✅ DONE |
| `risk_level` GREEN/YELLOW/ORANGE/RED classification | ✅ DONE |
| `veto_narrative` structured explainability | ✅ DONE |
| Tests written and targeted validation run | ✅ DONE |
| Existing brakes and risk modules unchanged | ✅ DONE |

**Phase 7 is COMPLETE.**

## 9. Validation Command

```powershell
python -m pytest tests/unit/test_phase7_risk_os.py -q --tb=short
```
