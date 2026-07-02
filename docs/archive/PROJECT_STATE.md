# Project State

This file is the current operational truth for the repository.

If a new AI agent starts, this is the first status file it should read after
the master roadmap.

## Updated At

2026-04-08 19:30:00 +03:00

## Current Phase

V1 Roadmap (all 10 phases COMPLETE):

1. Phase 1 - Core Reliability - COMPLETE (coverage ~85.03%)
2. Phase 2 - Paper Trading Rehabilitation - COMPLETE (2026-04-07)
3. Phase 3 - Measurement and Memory - COMPLETE (2026-04-06)
4. Phase 4 - Data Layer - COMPLETE (2026-04-08)
5. Phase 5 - Research and Backtesting Engine - COMPLETE (2026-04-08)
6. Phase 6 - Alpha Factory - COMPLETE (2026-04-08)
7. Phase 7 - Risk Operating System - COMPLETE (2026-04-08)
8. Phase 8 - Execution OS - COMPLETE (2026-04-08)
9. Phase 9 - Experiment and Promotion OS - COMPLETE (2026-04-08)
10. Phase 10 - Continuous Learning OS - COMPLETE (2026-04-08)

V2 Roadmap (docs/MASTER_ROADMAP_V2.md):

11. Phase 11 - Model Training Pipeline - COMPLETE (2026-04-08, see docs/phase11_model_training.md)
12. Phase 12 - Signal Validation & IC Measurement - IN PROGRESS (accumulating trades)
13. Phase 13 - Live Promotion Path - PENDING
14. Phase 14 - Multi-Asset Expansion - PENDING
15. Phase 15 - Alternative Data Layer - PENDING
16. Phase 16 - Tiny Live & First Real Capital - PENDING

## Current Runtime Truth

- main operating mode: `robust_paper`
- live trading: disabled
- Azure container rebuilt and restarted on 2026-04-08 ~19:25 +03:00
- All 4 models loaded (no fallback): XGB Sharpe=1.15, LGBM=0.55, LSTM=0.57
- Transformer excluded from ensemble (rejected: degenerate_constant_output)
- LearningOS background loop active (hourly, calls run_cycle(), persists to DB)
- scripts/ now included in Docker image (training executable inside container)
- Model retraining launched: python /app/scripts/train_models.py (background, /app/data/training.log)
- Weekly retrain scheduler: scripts/retrain_schedule.py

## High-Confidence Findings

### 1. Paper-mode trade starvation - fixed and deployed (2026-04-08)

Root cause: `RISK_COMMITTEE:ModelDisagreement` blocked signals with
`confidence < 0.20` before the paper floor override was reached.

Fix applied: `get_paper_risk_committee()` now uses `min_confidence=0.05`
(down from 0.20) and `max_model_disagreement=0.5` (up from 0.4).

Azure redeploy completed on 2026-04-08 around 15:48 +03:00; `/health` returns
`ok`.

### 2. Phase 6 Alpha Factory exit gate - met (2026-04-08)

Added:

- signal retirement persistence to `quant_analytics.db`
- model attribution wiring from `ChampionChallengerRegistry`
- dedicated `/api/signal_scorecard` endpoint

The platform can now expose per-signal IC/IR retirement evidence and per-model
attribution from a single operator-facing scorecard.

### 3. Paper runtime after redeploy

Latest Azure `/api/paper_health` snapshot on 2026-04-08:

- `sample_starved=false`
- dominant skip reason still `RISK_BLOCKED:normal`
- `RISK_COMMITTEE:ModelDisagreement` is present historically but not dominant

### 4. Metrics lifecycle is noisy

Port `9090` bind warning on restart - `reuse_address=True` already set; minor.

## Current Known Validation State

Latest targeted validation run on 2026-04-08:

- `ruff check wallet_manager/signal_intelligence.py wallet_manager/strategies/model_registry.py wallet_manager/metrics_server.py tests/unit/test_phase6_signal_scorecard.py tests/unit/test_metrics_server.py tests/unit/test_model_registry.py` -> pass
- `pytest tests/unit/test_phase4_data_layer.py tests/unit/test_phase5_backtester.py tests/unit/test_phase6_signal_scorecard.py tests/unit/test_metrics_server.py tests/unit/test_model_registry.py -q` -> **104 passed**
- Azure VM: `python3 -m compileall wallet_manager/risk_committee.py wallet_manager/signal_intelligence.py wallet_manager/strategies/model_registry.py wallet_manager/metrics_server.py` -> pass
- Azure runtime checks:
  - `/health` -> ok
  - `/api/signal_scorecard` -> 200 OK
  - `/api/paper_health` -> `sample_starved=false`

Working rule for future sessions:

- do not rerun the full `3155`-test suite after every small edit
- use targeted module/subsystem tests during iteration
- rerun the canonical full-suite commands only after meaningful checkpoints

## Immediate Priorities

- [x] Phase 1 complete - coverage ~85.03%
- [x] Phase 2 complete - documented in `docs/phase2_paper_rehab.md`
- [x] Phase 3 complete - decision journal, session tracking, CSV export, `/api/decisions`
- [x] Dashboard 12 bugs fixed (1 HIGH, 4 MEDIUM, 7 LOW)
- [x] Phase 4 complete - versioned datasets, feature persistence, replay, deterministic load
- [x] Paper-mode ModelDisagreement blocker fixed and deployed
- [x] Phase 5 complete - EventDrivenBacktester, BacktestReport, 26 tests
- [x] Phase 6 complete - signal retirement DB, model attribution, `/api/signal_scorecard`
- [x] Phase 7 complete - RiskOS, RiskStateSnapshot, RiskStateStore, `/api/risk_state`, `/risk_state` Telegram cmd (44 tests)
- [x] Phase 8 complete - ExecutionOS, ExecutionRecord, ExecutionRecordStore, `/api/execution_os`, `/execution_os` Telegram cmd
- [x] Phase 9 complete - PromotionOS, stage-gated rollout, PromotionStore, `/api/promotion_os`, `/promotion_os` Telegram cmd
- [x] Phase 10 complete - LearningOS, LearningCycle, LearningCycleStore, `/api/learning_os`, `/learning_os` Telegram cmd

## Files Most Likely To Change Next

- Azure deployment (Phases 7–10 not yet deployed)
- `deployment/AZURE_RUNTIME.md`
- `docs/HANDOFF.md`

## Repo Documentation Structure

These are the only docs a new AI agent needs for continuity:

1. `docs/MASTER_ROADMAP.md`
2. `docs/PROJECT_STATE.md`
3. `docs/HANDOFF.md`
4. `deployment/AZURE_RUNTIME.md`
