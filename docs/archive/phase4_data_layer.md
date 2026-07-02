# Phase 4 — Data Layer

## 1. Goal

Upgrade from ad hoc runtime data to quant-grade data infrastructure.

Research must be rerunnable deterministically from persisted data artifacts.

## 2. Scope

- Versioned historical datasets with explicit manifests
- Replayable data windows (named slices for train/test/backtest)
- Feature contracts (registry of every feature used in model inference)
- Data quality SLOs (governance and stale-data prevention)

## 3. New Modules

All Phase 4 code lives under `wallet_manager/data/`:

| Module | Class(es) | Purpose |
|---|---|---|
| `dataset_manifest.py` | `DatasetManifest`, `DatasetRegistry` | Versioned dataset records |
| `data_slice.py` | `DataSlice`, `SliceRegistry` | Replayable, labeled data windows |
| `feature_registry.py` | `FeatureSpec`, `FeatureRegistry` | Feature contracts and built-in specs |
| `data_quality.py` | `DataQualitySLA`, `DataQualityMonitor`, `DataQualityReport`, `ValidationResult` | Governance and SLO enforcement |

### 3.1 DatasetManifest / DatasetRegistry

Tracks every dataset version used for research or training.

Key fields:
- `dataset_id` — unique ID (e.g. `"ds_eth_5m_2024Q1_v1"`)
- `version` — semver string
- `data_start_ts / data_end_ts` — Unix epoch bounds
- `row_count` — number of candles
- `source_priority` — ordered list of data sources
- `preprocessing` — gap fill params, spike thresholds, etc.
- `quality` — measured quality metrics at creation time
- `checksum` — `sha256:<hex>` of dataset content (reproducibility)
- `associated_models` — list of model versions trained on this dataset
- `deprecated` — soft-delete flag (preserves audit trail)

Stored in: `dataset_registry.db`

### 3.2 DataSlice / SliceRegistry

Named, bounded windows of data for train/test/backtest/validation.

Key fields:
- `slice_id` — unique ID (e.g. `"slice_train_2024Q1_fold2"`)
- `dataset_id` — parent manifest reference
- `purpose` — `"train"` | `"test"` | `"validation"` | `"backtest"` | `"live_shadow"`
- `start_ts / end_ts` — epoch bounds of this slice
- `fold_index` — walk-forward fold number (-1 if not part of WF split)
- `associated_models` — models trained/evaluated on this slice

`SliceRegistry.list_walk_forward_folds(dataset_id)` returns ordered
`(train_slice, test_slice)` pairs for every fold.

Stored in: `dataset_registry.db` (same DB as DatasetRegistry)

### 3.3 FeatureSpec / FeatureRegistry / FeatureStore

Every feature used in model training or inference is declared here.

Key fields per FeatureSpec:
- `name` — unique feature name
- `version` — semver; increment when formula or inputs change
- `formula` — human-readable computation description
- `inputs` — source fields this feature depends on
- `output_type` — Python type name
- `output_range` — valid `(min, max)` bounds
- `stale_after_seconds` — max age before value is considered stale

**10 built-in specs** registered automatically on `initialize()`:
`garch_sigma`, `kalman_price`, `ofi_5m`, `realized_vol_5m`, `realized_vol_30m`,
`momentum_5`, `momentum_30`, `vol_regime`, `kyle_lambda`, `amihud_ratio`

**FeatureStore** — persists computed feature values alongside candles.

- `write_batch(timestamp, features, dataset_id)` — idempotent batch write
- `load(feature_names, dataset_id, start_ts, end_ts)` — filtered reload for replay
- `count(dataset_id)` — audit count

Table: `computed_features(timestamp, feature_name, value, dataset_id, computed_at)`

Unique index on `(timestamp, feature_name, dataset_id)` — re-running the pipeline
is safe and idempotent.

Stored in: `dataset_registry.db`

### 3.4 DataQualitySLA / DataQualityMonitor

Validates datasets against explicit quality thresholds before use.

SLA fields:
- `min_row_count` — minimum rows required
- `max_missing_pct` — maximum missing value percentage
- `max_spike_count` — maximum spike-flagged rows
- `max_stale_count` — maximum stale-flagged rows
- `max_purge_zone_pct` — maximum purge zone percentage
- `required_sources` — required data source presence
- `staleness_threshold_seconds` — max data age

Every validation result is persisted to `data_quality_audits` table for audit.

Stored in: `dataset_registry.db`

## 4. Database

**New file**: `dataset_registry.db`

Tables created automatically on first `initialize()`:
- `dataset_manifests`
- `data_slices`
- `feature_specs`
- `computed_features`
- `data_quality_audits`

Env var override: `DATASET_REGISTRY_DB_PATH`

## 5. Tests

`tests/unit/test_phase4_data_layer.py` — **38 tests, all pass**

Coverage:
- `DatasetManifest` — summary, duration, checksum, roundtrip, deprecated flag
- `DatasetRegistry` — register, get, list, deprecate, model association
- `DataSlice` — duration, summary, roundtrip
- `SliceRegistry` — register, get, list by purpose, walk-forward fold pairs
- `FeatureSpec` — stale detection, range check, summary, roundtrip
- `FeatureRegistry` — built-ins registered, register, get, deprecate
- `FeatureStore` — write, idempotent write, filter by name, filter by ts range, count, empty load
- `DataQualityMonitor` — pass/fail for each SLA dimension, record, recent_failures

## 6. Deliverables Completed

- [x] Integrate `DatasetRegistry` into `scripts/data/historical_data_pipeline.py`
  — `_register_manifest()` called at end of every `run()`
- [x] `load_for_training(dataset_id=None)` — deterministic replay: same `dataset_id`
  always loads the same candle window (Phase 4 Data Contract §10.7)
- [x] Integrate `SliceRegistry` into `wallet_manager/strategies/wf_validator.py`
  — `_register_slices()` uses `r.timestamp` for accurate fold boundaries (not `time.time()`)
- [x] Tick-to-bar aggregation: `wallet_manager/tick_collector.py`
  — `aggregate_ticks_to_bars(start_ts, end_ts, bar_seconds)` added
- [x] Wire `DataQualityMonitor` into pipeline — `_run_quality_gate()` runs after every `historical_data_pipeline.run()`
- [x] Add `/api/data_quality` endpoint to `metrics_server.py`
- [x] Add `/api/datasets` endpoint to `metrics_server.py`
- [x] `FeatureStore` — persists computed feature values to `computed_features` table

## 7. Exit Gate — COMPLETE (2026-04-08)

- [x] `historical_data_pipeline.py` auto-registers `DatasetManifest` after each run
- [x] `load_for_training(dataset_id)` loads only candles within that manifest's
  `data_start_ts/data_end_ts` → same `dataset_id` → same data (reproducible research)
- [x] `wf_validator.py` persists walk-forward splits as `DataSlice` records with
  accurate timestamps derived from `ValidationResult.timestamp`
- [x] `FeatureRegistry` has all 10 built-in feature specs
- [x] `FeatureStore` persists computed feature values for replay without recomputation
- [x] `TickCollector.aggregate_ticks_to_bars()` available for replay
- [x] `DataQualityMonitor` runs after every pipeline run (`_run_quality_gate`)
- [x] 38 unit tests pass (`pytest tests/unit/test_phase4_data_layer.py -q`)
- [x] `/api/data_quality` + `/api/datasets` endpoints in `metrics_server.py`
