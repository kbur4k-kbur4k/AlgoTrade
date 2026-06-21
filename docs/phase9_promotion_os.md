# Phase 9 — Experiment and Promotion Operating System

## Status

**COMPLETE** — 2026-04-08

## Goal (roadmap §15.1)

Promote only evidence-backed behavior through a controlled rollout path.

## Design

Phase 9 follows the same OS-facade pattern as Phases 7–8.

### Components

```
wallet_manager/promotion_os.py
├── ExperimentStage      PAPER → SHADOW → TINY_LIVE → SCALED_LIVE → RETIRED
├── PromotionGate        threshold-checked evidence record (one per metric)
├── PromotionRecord      per-experiment state + history (gates_passed/failed)
├── PromotionStore       SQLite persistence → quant_analytics.db
├── PromotionOS          Facade: register, evaluate, promote, demote, retire
└── get_promotion_os()   Process-wide singleton
```

Underlying module (pre-existing, extended by Phase 9):

```
wallet_manager/experiment_lab.py
├── ThresholdVariant     A/B threshold configuration
├── FeatureToggleVariant feature enable/disable variant
├── RegimeVariant        regime-specific strategy variant
├── ExperimentLab        shadow observation + cycle recording
└── get_experiment_lab() singleton
```

## Rollout Stages

| Stage       | Description |
|-------------|-------------|
| PAPER       | Shadow paper mode; observe without capital |
| SHADOW      | On-chain shadow with paper fill; compare routes |
| TINY_LIVE   | Micro capital (1-2% of budget) live execution |
| SCALED_LIVE | Full capital allocation on proven behavior |
| RETIRED     | Terminal; alpha decayed or replaced |

## Stage Gates (default thresholds)

| Transition            | Gate Metrics |
|-----------------------|-------------|
| PAPER → SHADOW        | min_cycles ≥ 50, agreement_pct ≥ 60 |
| SHADOW → TINY_LIVE    | min_cycles ≥ 100, shared_realized_pnl ≥ 0, agreement_pct ≥ 65 |
| TINY_LIVE → SCALED_LIVE | min_cycles ≥ 200, shared_realized_pnl ≥ 5, agreement_pct ≥ 70 |

## Data Model

### PromotionRecord

| Field             | Type    | Description |
|-------------------|---------|-------------|
| record_id         | str     | UUID |
| experiment_name   | str     | Unique identifier |
| current_stage     | str     | ExperimentStage value |
| promoted_at       | float   | Last promotion timestamp |
| demoted_at        | float   | Last demotion timestamp |
| promotion_count   | int     | Total promotions |
| demotion_count    | int     | Total demotions |
| gates_passed      | list    | Passing PromotionGate dicts |
| gates_failed      | list    | Failing PromotionGate dicts |
| rollback_rule     | str     | Demotion trigger description |

### Database Tables

- `promotion_records` — one row per experiment (upserted)
- `promotion_gates` — append-only gate evaluations

## API

| Endpoint             | Description |
|----------------------|-------------|
| `/api/promotion_os`  | Phase 9 scorecard: stage counts, experiment list, lab winner |
| `/api/experiments`   | ExperimentLab variant report (pre-existing) |

## Telegram Command

`/promotion_os` — Shows:
- Total experiments registered
- Per-stage count breakdown
- ExperimentLab winner (if data available)

## Exit Gate (roadmap §15.7)

> The platform can safely move behavior from paper to capital with evidence.

Criteria met:

- [x] `ExperimentStage` models full rollout path
- [x] `PromotionGate` records threshold evidence per transition
- [x] `PromotionOS.promote()` is blocked by gate failures
- [x] `PromotionOS.demote()` supports rollback
- [x] `/api/promotion_os` returns 200 + scorecard
- [x] `/promotion_os` Telegram command
- [x] All tests pass (`test_phase9_promotion_os.py`)

## Test File

`tests/unit/test_phase9_promotion_os.py` — covers:
- `ExperimentStage` + `_next_stage` helper
- `PromotionGate` and `PromotionRecord` dataclasses
- `PromotionStore` (tables, save/load/upsert, list, count)
- `PromotionOS` (register, evaluate, promote, demote, retire, multi-stage chain)
- Scorecard keys and content
- Singleton behaviour
- `/api/promotion_os` API handler + route registration
