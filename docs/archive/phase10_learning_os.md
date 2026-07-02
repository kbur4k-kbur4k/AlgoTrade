# Phase 10 — Continuous Learning Operating System

## Status

**COMPLETE** — 2026-04-08

## Goal (roadmap §16.1)

Keep the system adaptive without letting it drift into chaos.

## Design

Phase 10 follows the same OS-facade pattern as Phases 7–9.

### Components

```
wallet_manager/learning_os.py
├── LearningCycle        one complete evidence review snapshot
├── LearningCycleStore   SQLite persistence → quant_analytics.db
├── LearningOS           Facade: run_cycle() + get_scorecard()
└── get_learning_os()    Process-wide singleton
```

Underlying module (pre-existing, orchestrated by Phase 10):

```
wallet_manager/continuous_learning.py
├── DriftReviewer        concept drift trend monitoring (NOMINAL/MILD/MODERATE/SEVERE)
├── SetupDecayTracker    early-vs-recent PnL split per setup tag
├── ThresholdRetuner     evidence-based threshold suggestion generator
├── PerformanceChangelog persistent JSON log of strategy changes + outcomes
├── FeatureImportanceDrift JS-7.4 feature rank decay detection
└── ContinuousLearner   orchestrates all components
```

## Data Model

### LearningCycle

| Field                | Type    | Description |
|----------------------|---------|-------------|
| cycle_id             | str     | UUID |
| timestamp            | float   | Unix timestamp |
| drift_level          | str     | NOMINAL / MILD / MODERATE / SEVERE |
| drift_trend          | str     | stable / increasing / decreasing |
| drift_alert          | bool    | True if drift warrants action |
| setup_decay_count    | int     | Setups showing PnL decay |
| stable_setup_count   | int     | Stable setups |
| feature_alert_count  | int     | Feature importance decay alerts |
| suggestions_count    | int     | Threshold suggestions generated |
| alerts               | list    | Human-readable alert strings (capped at 20) |

### Database Table

`learning_cycles` in `quant_analytics.db`.

## API

| Endpoint            | Description |
|---------------------|-------------|
| `/api/learning_os`  | Phase 10 scorecard: aggregate stats, drift summary, feature drift, recent cycles |
| `/api/learning`     | ContinuousLearner snapshot (pre-existing) |
| `/api/feature_drift`| FeatureImportanceDrift state (pre-existing) |

## Telegram Command

`/learning_os` — Shows:
- Cycles recorded
- Total drift alerts
- Current drift level + trend
- Feature decay alerts
- Average suggestions per cycle

## Drift Alert Logic

An alert is raised when:
- `severe_count_last_10 >= 3` (three SEVERE readings in last 10 cycles), OR
- `trend == "increasing" AND avg_score_10 >= 2.0`

## No Autonomous Changes

All threshold suggestions and setup decay detections require human approval.
The system generates evidence; the operator decides. The `PerformanceChangelog`
records what was tried and what happened.

## Exit Gate (roadmap §16.7)

> The platform evolves with evidence instead of intuition.

Criteria met:

- [x] `LearningCycle` captures drift + decay + feature alerts in one record
- [x] `LearningCycleStore` persists cycles for historical review
- [x] `LearningOS.run_cycle()` wraps full ContinuousLearner report
- [x] `LearningOS.get_scorecard()` surfaces all learning signals
- [x] `/api/learning_os` returns 200 + scorecard
- [x] `/learning_os` Telegram command
- [x] All tests pass (`test_phase10_learning_os.py`)

## Test File

`tests/unit/test_phase10_learning_os.py` — covers:
- `LearningCycle` dataclass (fields, serialization, uniqueness)
- `LearningCycleStore` (table creation, save, get_recent, get_stats, count, limit)
- `LearningOS.run_cycle()` (mocked ContinuousLearner, drift mapping, alert flag, alert cap)
- Scorecard keys and content
- Singleton behaviour
- `/api/learning_os` API handler + route registration
