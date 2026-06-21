"""
tests/unit/test_phase4_data_layer.py
======================================
Phase 4 — Data Layer: Unit tests for dataset_manifest, data_slice,
feature_registry, and data_quality modules.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from wallet_manager.data.data_quality import (
    DataQualityMonitor,
    DataQualityReport,
    DataQualitySLA,
)
from wallet_manager.data.data_slice import DataSlice, SliceRegistry
from wallet_manager.data.dataset_manifest import DatasetManifest, DatasetRegistry
from wallet_manager.data.feature_registry import FeatureRegistry, FeatureSpec, FeatureStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):  # type: ignore[return]
    return asyncio.run(coro)


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_registry.db")


# ---------------------------------------------------------------------------
# DatasetManifest / DatasetRegistry
# ---------------------------------------------------------------------------

class TestDatasetManifest:
    def test_summary(self):
        m = DatasetManifest(
            dataset_id="ds_test_v1",
            version="1.0.0",
            data_start_ts=1_700_000_000,
            data_end_ts=1_700_000_000 + 86_400 * 30,
            row_count=8_640,
            source_priority=["uniswap_subgraph"],
            preprocessing={},
            quality={},
            checksum="sha256:abc",
        )
        assert "ds_test_v1" in m.summary()
        assert "8,640" in m.summary()

    def test_duration_days(self):
        m = DatasetManifest(
            dataset_id="ds_x",
            version="1.0",
            data_start_ts=0,
            data_end_ts=86_400 * 10,
            row_count=1,
            source_priority=[],
            preprocessing={},
            quality={},
            checksum="sha256:x",
        )
        assert m.duration_days() == pytest.approx(10.0)

    def test_checksum(self):
        cs = DatasetManifest.compute_checksum(b"hello")
        assert cs.startswith("sha256:")
        assert len(cs) > 10

    def test_roundtrip_dict(self):
        m = DatasetManifest(
            dataset_id="ds_rt",
            version="2.0",
            data_start_ts=100,
            data_end_ts=200,
            row_count=50,
            source_priority=["binance"],
            preprocessing={"gap_fill": 6},
            quality={"missing_pct": 0.1},
            checksum="sha256:rt",
            associated_models=["xgb_v1"],
            associated_strategy="momentum",
            deprecated=False,
            notes="test note",
        )
        d = m.to_dict()
        m2 = DatasetManifest.from_row(d)
        assert m2.dataset_id == m.dataset_id
        assert m2.source_priority == m.source_priority
        assert m2.preprocessing == m.preprocessing
        assert m2.quality == m.quality
        assert m2.associated_models == m.associated_models
        assert m2.deprecated == m.deprecated

    def test_deprecated_summary(self):
        m = DatasetManifest(
            dataset_id="old",
            version="1.0",
            data_start_ts=0,
            data_end_ts=86400,
            row_count=1,
            source_priority=[],
            preprocessing={},
            quality={},
            checksum="sha256:z",
            deprecated=True,
        )
        assert "DEPRECATED" in m.summary()


class TestDatasetRegistry:
    def test_register_and_get(self, tmp_db):
        reg = DatasetRegistry(db_path=tmp_db)
        m = DatasetManifest(
            dataset_id="ds_reg_test",
            version="1.0",
            data_start_ts=0,
            data_end_ts=86400,
            row_count=288,
            source_priority=["binance"],
            preprocessing={},
            quality={},
            checksum="sha256:r1",
        )
        _run(reg.register(m))
        m2 = _run(reg.get("ds_reg_test"))
        assert m2 is not None
        assert m2.dataset_id == "ds_reg_test"
        assert m2.row_count == 288

    def test_get_missing(self, tmp_db):
        reg = DatasetRegistry(db_path=tmp_db)
        result = _run(reg.get("nonexistent"))
        assert result is None

    def test_list_all(self, tmp_db):
        reg = DatasetRegistry(db_path=tmp_db)
        for i in range(3):
            m = DatasetManifest(
                dataset_id=f"ds_{i}",
                version="1.0",
                data_start_ts=i,
                data_end_ts=i + 86400,
                row_count=i + 1,
                source_priority=[],
                preprocessing={},
                quality={},
                checksum=f"sha256:{i}",
            )
            _run(reg.register(m))
        results = _run(reg.list_all())
        assert len(results) == 3

    def test_deprecate(self, tmp_db):
        reg = DatasetRegistry(db_path=tmp_db)
        m = DatasetManifest(
            dataset_id="ds_dep",
            version="1.0",
            data_start_ts=0,
            data_end_ts=1,
            row_count=1,
            source_priority=[],
            preprocessing={},
            quality={},
            checksum="sha256:dep",
        )
        _run(reg.register(m))
        _run(reg.deprecate("ds_dep", "old data"))
        # Should not appear in list_all (deprecated=False filter)
        active = _run(reg.list_all(include_deprecated=False))
        assert not any(x.dataset_id == "ds_dep" for x in active)
        # Should appear when including deprecated
        all_records = _run(reg.list_all(include_deprecated=True))
        assert any(x.dataset_id == "ds_dep" for x in all_records)

    def test_add_model_association(self, tmp_db):
        reg = DatasetRegistry(db_path=tmp_db)
        m = DatasetManifest(
            dataset_id="ds_model",
            version="1.0",
            data_start_ts=0,
            data_end_ts=1,
            row_count=1,
            source_priority=[],
            preprocessing={},
            quality={},
            checksum="sha256:m",
        )
        _run(reg.register(m))
        _run(reg.add_model_association("ds_model", "xgb_v2"))
        updated = _run(reg.get("ds_model"))
        assert updated is not None
        assert "xgb_v2" in updated.associated_models


# ---------------------------------------------------------------------------
# DataSlice / SliceRegistry
# ---------------------------------------------------------------------------

class TestDataSlice:
    def test_duration_days(self):
        sl = DataSlice(
            slice_id="sl_test",
            dataset_id="ds_x",
            purpose="train",
            start_ts=0,
            end_ts=86_400 * 7,
            row_count=2016,
        )
        assert sl.duration_days() == pytest.approx(7.0)

    def test_summary(self):
        sl = DataSlice(
            slice_id="sl_sum",
            dataset_id="ds_x",
            purpose="test",
            start_ts=0,
            end_ts=86_400,
            row_count=288,
            fold_index=2,
        )
        s = sl.summary()
        assert "sl_sum" in s
        assert "test" in s
        assert "fold=2" in s

    def test_roundtrip_dict(self):
        sl = DataSlice(
            slice_id="sl_rt",
            dataset_id="ds_rt",
            purpose="validation",
            start_ts=1000,
            end_ts=2000,
            row_count=10,
            fold_index=1,
            associated_models=["lstm_v1"],
            notes="rt",
        )
        d = sl.to_dict()
        sl2 = DataSlice.from_row(d)
        assert sl2.slice_id == sl.slice_id
        assert sl2.associated_models == sl.associated_models
        assert sl2.fold_index == 1


class TestSliceRegistry:
    def test_register_and_get(self, tmp_db):
        reg = SliceRegistry(db_path=tmp_db)
        sl = DataSlice(
            slice_id="sl_reg",
            dataset_id="ds_x",
            purpose="train",
            start_ts=0,
            end_ts=86400,
            row_count=288,
        )
        _run(reg.register(sl))
        sl2 = _run(reg.get("sl_reg"))
        assert sl2 is not None
        assert sl2.row_count == 288

    def test_get_missing(self, tmp_db):
        reg = SliceRegistry(db_path=tmp_db)
        assert _run(reg.get("missing")) is None

    def test_list_by_dataset_and_purpose(self, tmp_db):
        reg = SliceRegistry(db_path=tmp_db)
        for purpose, n in [("train", 0), ("test", 1), ("train", 2)]:
            _run(reg.register(DataSlice(
                slice_id=f"sl_{purpose}_{n}",
                dataset_id="ds_list",
                purpose=purpose,  # type: ignore[arg-type]
                start_ts=n * 86400,
                end_ts=(n + 1) * 86400,
                row_count=288,
            )))
        trains = _run(reg.list_by_dataset("ds_list", "train"))
        assert len(trains) == 2
        tests = _run(reg.list_by_dataset("ds_list", "test"))
        assert len(tests) == 1

    def test_walk_forward_folds(self, tmp_db):
        reg = SliceRegistry(db_path=tmp_db)
        for fold in range(3):
            for purpose in ("train", "test"):
                _run(reg.register(DataSlice(
                    slice_id=f"sl_wf_{purpose}_{fold}",
                    dataset_id="ds_wf",
                    purpose=purpose,  # type: ignore[arg-type]
                    start_ts=fold * 86400,
                    end_ts=(fold + 1) * 86400,
                    row_count=100,
                    fold_index=fold,
                )))
        pairs = _run(reg.list_walk_forward_folds("ds_wf"))
        assert len(pairs) == 3
        assert all(tr.purpose == "train" and te.purpose == "test" for tr, te in pairs)


# ---------------------------------------------------------------------------
# FeatureSpec / FeatureRegistry
# ---------------------------------------------------------------------------

class TestFeatureSpec:
    def test_is_stale(self):
        spec = FeatureSpec(name="f", stale_after_seconds=60)
        assert spec.is_stale(last_computed_ts=time.time() - 120)
        assert not spec.is_stale(last_computed_ts=time.time() - 10)

    def test_is_in_range(self):
        spec = FeatureSpec(name="f", output_range=(-1.0, 1.0))
        assert spec.is_in_range(0.5)
        assert not spec.is_in_range(1.5)
        spec_no_range = FeatureSpec(name="g")
        assert spec_no_range.is_in_range(999.0)

    def test_summary(self):
        spec = FeatureSpec(name="ofi", version="2.0", output_range=(-1.0, 1.0))
        s = spec.summary()
        assert "ofi" in s
        assert "2.0" in s

    def test_roundtrip(self):
        spec = FeatureSpec(
            name="test_feat",
            version="1.1",
            description="test",
            formula="x + y",
            inputs=["a", "b"],
            output_type="float",
            output_range=(0.0, 100.0),
            stale_after_seconds=120,
        )
        d = spec.to_dict()
        spec2 = FeatureSpec.from_row(d)
        assert spec2.name == spec.name
        assert spec2.output_range == spec.output_range
        assert spec2.inputs == spec.inputs


class TestFeatureRegistry:
    def test_builtins_registered(self, tmp_db):
        reg = FeatureRegistry(db_path=tmp_db)
        _run(reg.initialize())
        specs = _run(reg.list_all())
        assert len(specs) >= 10
        names = {s.name for s in specs}
        assert "garch_sigma" in names
        assert "ofi_5m" in names
        assert "vol_regime" in names

    def test_register_and_get(self, tmp_db):
        reg = FeatureRegistry(db_path=tmp_db)
        spec = FeatureSpec(name="custom_feat", version="1.0", description="custom")
        _run(reg.register(spec))
        fetched = _run(reg.get("custom_feat"))
        assert fetched is not None
        assert fetched.description == "custom"

    def test_get_missing(self, tmp_db):
        reg = FeatureRegistry(db_path=tmp_db)
        assert _run(reg.get("no_such_feat")) is None

    def test_deprecate(self, tmp_db):
        reg = FeatureRegistry(db_path=tmp_db)
        spec = FeatureSpec(name="old_feat")
        _run(reg.register(spec))
        _run(reg.deprecate("old_feat", "replaced by new_feat"))
        active = _run(reg.list_all(include_deprecated=False))
        assert not any(s.name == "old_feat" for s in active)


# ---------------------------------------------------------------------------
# DataQualitySLA / DataQualityMonitor
# ---------------------------------------------------------------------------

class TestDataQualitySLA:
    def test_passes_when_all_ok(self):
        monitor = DataQualityMonitor()
        sla = DataQualitySLA(
            dataset_id="ds_q",
            min_row_count=100,
            max_missing_pct=5.0,
            max_spike_count=10,
            max_stale_count=5,
            required_sources=[],
        )
        report = DataQualityReport(
            dataset_id="ds_q",
            row_count=500,
            missing_pct=1.0,
            spike_count=2,
            stale_count=0,
        )
        result = monitor.validate(report, sla)
        assert result.passed
        assert result.violations == []

    def test_fails_row_count(self):
        monitor = DataQualityMonitor()
        sla = DataQualitySLA(dataset_id="ds_q", min_row_count=1000, required_sources=[])
        report = DataQualityReport(dataset_id="ds_q", row_count=500)
        result = monitor.validate(report, sla)
        assert not result.passed
        assert any("row_count" in v for v in result.violations)

    def test_fails_missing_pct(self):
        monitor = DataQualityMonitor()
        sla = DataQualitySLA(dataset_id="ds_q", min_row_count=1, max_missing_pct=1.0, required_sources=[])
        report = DataQualityReport(dataset_id="ds_q", row_count=100, missing_pct=5.0)
        result = monitor.validate(report, sla)
        assert not result.passed
        assert any("missing_pct" in v for v in result.violations)

    def test_fails_missing_sources(self):
        monitor = DataQualityMonitor()
        sla = DataQualitySLA(
            dataset_id="ds_q",
            min_row_count=1,
            required_sources=["uniswap_subgraph"],
        )
        report = DataQualityReport(
            dataset_id="ds_q",
            row_count=100,
            sources_present=["binance"],
        )
        result = monitor.validate(report, sla)
        assert not result.passed
        assert any("sources" in v for v in result.violations)

    def test_fails_staleness(self):
        monitor = DataQualityMonitor()
        sla = DataQualitySLA(
            dataset_id="ds_q",
            min_row_count=1,
            staleness_threshold_seconds=3600,
            required_sources=[],
        )
        old_ts = time.time() - 7200  # 2 hours ago
        report = DataQualityReport(
            dataset_id="ds_q",
            row_count=100,
            latest_row_ts=old_ts,
        )
        result = monitor.validate(report, sla)
        assert not result.passed
        assert any("days old" in v for v in result.violations)

    def test_record_and_last_result(self, tmp_db):
        monitor = DataQualityMonitor(db_path=tmp_db)
        sla = DataQualitySLA(dataset_id="ds_q", min_row_count=1, required_sources=[])
        report = DataQualityReport(dataset_id="ds_q", row_count=100)
        result = monitor.validate(report, sla)
        _run(monitor.record(result))
        last = _run(monitor.last_result("ds_q"))
        assert last is not None
        assert last["passed"] == 1

    def test_recent_failures(self, tmp_db):
        monitor = DataQualityMonitor(db_path=tmp_db)
        sla = DataQualitySLA(dataset_id="ds_fail", min_row_count=10000, required_sources=[])
        report = DataQualityReport(dataset_id="ds_fail", row_count=1)
        result = monitor.validate(report, sla)
        _run(monitor.record(result))
        failures = _run(monitor.recent_failures())
        assert len(failures) >= 1
        assert failures[0]["dataset_id"] == "ds_fail"


# ---------------------------------------------------------------------------
# FeatureStore — Phase 4 feature persistence
# ---------------------------------------------------------------------------

class TestFeatureStore:
    def test_write_and_load(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        _run(store.write_batch(
            timestamp=1_700_000_300,
            features={"garch_sigma": 0.003, "momentum_5": 0.012},
            dataset_id="ds_test",
        ))
        rows = _run(store.load(dataset_id="ds_test"))
        assert len(rows) == 2
        names = {r["feature_name"] for r in rows}
        assert names == {"garch_sigma", "momentum_5"}

    def test_idempotent_write(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        for _ in range(3):
            _run(store.write_batch(
                timestamp=1_700_000_600,
                features={"realized_vol_5m": 0.55},
                dataset_id="ds_idem",
            ))
        rows = _run(store.load(dataset_id="ds_idem"))
        assert len(rows) == 1  # INSERT OR REPLACE keeps only one

    def test_filter_by_feature_name(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        _run(store.write_batch(
            timestamp=1_700_001_000,
            features={"garch_sigma": 0.002, "ofi_5m": 0.1, "momentum_5": -0.005},
            dataset_id="ds_filter",
        ))
        rows = _run(store.load(feature_names=["garch_sigma", "ofi_5m"], dataset_id="ds_filter"))
        assert len(rows) == 2
        assert all(r["feature_name"] in {"garch_sigma", "ofi_5m"} for r in rows)

    def test_filter_by_timestamp_range(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        for ts in [1_000, 2_000, 3_000]:
            _run(store.write_batch(timestamp=ts, features={"garch_sigma": 0.001 * ts}, dataset_id=""))
        rows = _run(store.load(start_ts=1_500, end_ts=2_500))
        assert len(rows) == 1
        assert rows[0]["timestamp"] == 2_000

    def test_count(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        _run(store.write_batch(1_000, {"a": 1.0, "b": 2.0}, dataset_id="ds_cnt"))
        _run(store.write_batch(2_000, {"a": 1.5}, dataset_id="ds_cnt"))
        assert _run(store.count("ds_cnt")) == 3
        assert _run(store.count("other")) == 0

    def test_empty_load(self, tmp_db):
        store = FeatureStore(db_path=tmp_db)
        rows = _run(store.load(dataset_id="nonexistent"))
        assert rows == []
