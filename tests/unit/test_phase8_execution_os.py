"""
tests/unit/test_phase8_execution_os.py

Phase 8 — Execution Operating System
======================================
Tests for:
  - ExecutionRecord dataclass
  - ExecutionRecordStore (SQLite persistence)
  - ExecutionOS facade (record_trade, get_scorecard)
  - Singleton accessor
  - /api/execution_os handler (via build_app)
  - Bug-fix regressions: _pending_twaps, shortfall_tracker attribute
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# ExecutionRecord
# ---------------------------------------------------------------------------


class TestExecutionRecord:
    def test_defaults(self) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        r = ExecutionRecord()
        assert r.direction == "BUY"
        assert r.size_usd == 0.0
        assert r.route_dex == ""
        assert r.shadow_deviation_pct is None
        assert len(r.record_id) == 36  # UUID

    def test_to_dict_keys(self) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        r = ExecutionRecord(
            direction="SELL",
            size_usd=500.0,
            route_dex="uniswap_v3",
            route_savings_bps=12.5,
            estimated_slippage_bps=8.0,
            actual_slippage_bps=9.3,
            execution_shortfall=0.0003,
            cost_attribution_usd=0.465,
            shadow_deviation_pct=0.041,
            notes="test",
        )
        d = r.to_dict()
        assert d["direction"] == "SELL"
        assert d["size_usd"] == 500.0
        assert d["route_dex"] == "uniswap_v3"
        assert d["route_savings_bps"] == 12.5
        assert d["estimated_slippage_bps"] == 8.0
        assert d["actual_slippage_bps"] == 9.3
        assert d["shadow_deviation_pct"] == 0.041
        assert "record_id" in d
        assert "timestamp" in d

    def test_shadow_deviation_none_serializes(self) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        r = ExecutionRecord(shadow_deviation_pct=None)
        d = r.to_dict()
        assert d["shadow_deviation_pct"] is None

    def test_unique_record_ids(self) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        ids = {ExecutionRecord().record_id for _ in range(10)}
        assert len(ids) == 10

    def test_rounding_in_to_dict(self) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        r = ExecutionRecord(
            estimated_slippage_bps=8.123456789,
            actual_slippage_bps=9.987654321,
            execution_shortfall=0.000123456,
        )
        d = r.to_dict()
        assert len(str(d["estimated_slippage_bps"])) <= 8
        assert len(str(d["actual_slippage_bps"])) <= 8


# ---------------------------------------------------------------------------
# ExecutionRecordStore
# ---------------------------------------------------------------------------


class TestExecutionRecordStore:
    def _make_store(self, tmp_path: Path):
        from wallet_manager.execution_os import ExecutionRecordStore
        return ExecutionRecordStore(db_path=tmp_path / "test_exec.db")

    def test_table_created(self, tmp_path: Path) -> None:
        import sqlite3
        self._make_store(tmp_path)
        db_path = tmp_path / "test_exec.db"
        with sqlite3.connect(db_path) as conn:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        assert "execution_records" in names

    def test_save_and_get_recent(self, tmp_path: Path) -> None:
        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        r = ExecutionRecord(direction="BUY", size_usd=100.0, route_dex="uniswap_v3")
        ok = store.save(r)
        assert ok is True
        recent = store.get_recent(5)
        assert len(recent) == 1
        assert recent[0]["direction"] == "BUY"

    def test_get_recent_returns_newest_first(self, tmp_path: Path) -> None:
        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        for i in range(5):
            store.save(ExecutionRecord(size_usd=float(i), timestamp=float(i)))
        recent = store.get_recent(5)
        assert recent[0]["size_usd"] >= recent[-1]["size_usd"]

    def test_get_recent_limit(self, tmp_path: Path) -> None:
        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        for _ in range(10):
            store.save(ExecutionRecord())
        assert len(store.get_recent(3)) == 3

    def test_get_stats_empty(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        stats = store.get_stats()
        assert stats["total_records"] == 0
        assert stats["avg_actual_slippage_bps"] == 0.0

    def test_get_stats_populated(self, tmp_path: Path) -> None:
        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        store.save(ExecutionRecord(
            actual_slippage_bps=10.0,
            estimated_slippage_bps=8.0,
            route_savings_bps=5.0,
            cost_attribution_usd=0.5,
        ))
        store.save(ExecutionRecord(
            actual_slippage_bps=6.0,
            estimated_slippage_bps=7.0,
            route_savings_bps=3.0,
            cost_attribution_usd=0.3,
        ))
        stats = store.get_stats()
        assert stats["total_records"] == 2
        assert abs(stats["avg_actual_slippage_bps"] - 8.0) < 0.01
        assert abs(stats["avg_estimated_slippage_bps"] - 7.5) < 0.01
        assert abs(stats["avg_route_savings_bps"] - 4.0) < 0.01
        assert abs(stats["total_cost_usd"] - 0.8) < 0.001

    def test_raw_json_stored(self, tmp_path: Path) -> None:
        import sqlite3

        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        r = ExecutionRecord(direction="SELL", size_usd=200.0)
        store.save(r)
        db_path = tmp_path / "test_exec.db"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT raw_json FROM execution_records WHERE record_id=?",
                (r.record_id,),
            ).fetchone()
        assert row is not None
        d = json.loads(row[0])
        assert d["direction"] == "SELL"

    def test_shadow_deviation_none_stored(self, tmp_path: Path) -> None:
        import sqlite3

        from wallet_manager.execution_os import ExecutionRecord, ExecutionRecordStore
        store = ExecutionRecordStore(db_path=tmp_path / "test_exec.db")
        r = ExecutionRecord(shadow_deviation_pct=None)
        store.save(r)
        db_path = tmp_path / "test_exec.db"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT shadow_deviation_pct FROM execution_records WHERE record_id=?",
                (r.record_id,),
            ).fetchone()
        assert row[0] is None


# ---------------------------------------------------------------------------
# ExecutionOS facade
# ---------------------------------------------------------------------------


class TestExecutionOS:
    def _make_eos(self, tmp_path: Path):
        from wallet_manager.execution_os import ExecutionOS
        return ExecutionOS(db_path=tmp_path / "exec_os_test.db")

    def test_record_trade_returns_execution_record(self, tmp_path: Path) -> None:
        from wallet_manager.execution_os import ExecutionRecord
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="BUY",
            size_usd=250.0,
            route_dex="uniswap_v3",
            route_savings_bps=8.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=6.0,
        )
        assert isinstance(record, ExecutionRecord)
        assert record.direction == "BUY"
        assert record.size_usd == 250.0

    def test_execution_shortfall_buy(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="BUY",
            size_usd=100.0,
            route_dex="uniswap_v3",
            route_savings_bps=0.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=5.0,
            arrival_price=2000.0,
            fill_price=2010.0,
        )
        expected_is = (2010.0 - 2000.0) / 2000.0
        assert abs(record.execution_shortfall - expected_is) < 1e-9

    def test_execution_shortfall_sell_negated(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="SELL",
            size_usd=100.0,
            route_dex="uniswap_v3",
            route_savings_bps=0.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=5.0,
            arrival_price=2000.0,
            fill_price=1990.0,
        )
        raw = (1990.0 - 2000.0) / 2000.0  # negative
        expected_is = -raw  # negated for sell
        assert abs(record.execution_shortfall - expected_is) < 1e-9

    def test_cost_attribution_calculation(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="BUY",
            size_usd=1000.0,
            route_dex="sushiswap",
            route_savings_bps=5.0,
            estimated_slippage_bps=10.0,
            actual_slippage_bps=10.0,
            gas_cost_usd=0.5,
        )
        expected_slippage_cost = 1000.0 * 10.0 / 10_000.0
        assert abs(record.cost_attribution_usd - (expected_slippage_cost + 0.5)) < 1e-6

    def test_shadow_deviation_passed_through(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="BUY",
            size_usd=100.0,
            route_dex="uniswap_v3",
            route_savings_bps=0.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=5.0,
            shadow_deviation_pct=0.07,
        )
        assert record.shadow_deviation_pct == 0.07

    def test_record_persisted_to_store(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        eos.record_trade(
            direction="BUY",
            size_usd=50.0,
            route_dex="aerodrome",
            route_savings_bps=2.0,
            estimated_slippage_bps=3.0,
            actual_slippage_bps=4.0,
        )
        recent = eos._store.get_recent(5)
        assert len(recent) == 1
        assert recent[0]["route_dex"] == "aerodrome"

    def test_zero_arrival_price_no_shortfall(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        record = eos.record_trade(
            direction="BUY",
            size_usd=100.0,
            route_dex="uniswap_v3",
            route_savings_bps=0.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=5.0,
            arrival_price=0.0,
            fill_price=2000.0,
        )
        assert record.execution_shortfall == 0.0

    def test_multiple_records_accumulate(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        for _ in range(5):
            eos.record_trade(
                direction="BUY",
                size_usd=100.0,
                route_dex="uniswap_v3",
                route_savings_bps=5.0,
                estimated_slippage_bps=5.0,
                actual_slippage_bps=6.0,
            )
        stats = eos._store.get_stats()
        assert stats["total_records"] == 5


# ---------------------------------------------------------------------------
# ExecutionOS scorecard
# ---------------------------------------------------------------------------


class TestExecutionOSScorecard:
    def _make_eos(self, tmp_path: Path):
        from wallet_manager.execution_os import ExecutionOS
        return ExecutionOS(db_path=tmp_path / "scorecard_test.db")

    def test_scorecard_keys_present(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        sc = eos.get_scorecard()
        assert "generated_at" in sc
        assert "phase" in sc
        assert sc["phase"] == 8
        assert "store_stats" in sc
        assert "recent_records" in sc

    def test_scorecard_empty_store(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        sc = eos.get_scorecard()
        assert sc["store_stats"]["total_records"] == 0

    def test_scorecard_populated(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        eos.record_trade(
            direction="BUY",
            size_usd=200.0,
            route_dex="uniswap_v3",
            route_savings_bps=7.0,
            estimated_slippage_bps=5.0,
            actual_slippage_bps=6.5,
        )
        sc = eos.get_scorecard()
        assert sc["store_stats"]["total_records"] == 1
        assert len(sc["recent_records"]) == 1

    def test_scorecard_recent_records_limit(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        for _ in range(15):
            eos.record_trade(
                direction="SELL",
                size_usd=50.0,
                route_dex="sushiswap",
                route_savings_bps=3.0,
                estimated_slippage_bps=4.0,
                actual_slippage_bps=4.5,
            )
        sc = eos.get_scorecard()
        assert len(sc["recent_records"]) <= 10

    def test_scorecard_generated_at_recent(self, tmp_path: Path) -> None:
        eos = self._make_eos(tmp_path)
        sc = eos.get_scorecard()
        assert abs(sc["generated_at"] - time.time()) < 5.0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestExecutionOSSingleton:
    def test_singleton_returns_same_instance(self, tmp_path: Path) -> None:
        import wallet_manager.execution_os as eos_mod
        old = eos_mod._execution_os_instance
        eos_mod._execution_os_instance = None
        try:
            from wallet_manager.execution_os import get_execution_os
            a = get_execution_os(db_path=tmp_path / "singleton.db")
            b = get_execution_os(db_path=tmp_path / "singleton.db")
            assert a is b
        finally:
            eos_mod._execution_os_instance = old

    def test_singleton_not_none(self, tmp_path: Path) -> None:
        import wallet_manager.execution_os as eos_mod
        old = eos_mod._execution_os_instance
        eos_mod._execution_os_instance = None
        try:
            from wallet_manager.execution_os import get_execution_os
            inst = get_execution_os(db_path=tmp_path / "singleton2.db")
            assert inst is not None
        finally:
            eos_mod._execution_os_instance = old


# ---------------------------------------------------------------------------
# /api/execution_os handler
# ---------------------------------------------------------------------------


class TestExecutionOsApiHandler:
    @pytest.mark.asyncio
    async def test_handler_returns_status_ok(self) -> None:
        """_handle_execution_os_api builds a response with status ok."""
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_execution_os_api
        req = MagicMock()
        resp = await _handle_execution_os_api(req)
        data = _json.loads(resp.body)
        assert data["status"] == "ok"
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_handler_includes_execution_os_key(self) -> None:
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_execution_os_api
        req = MagicMock()
        resp = await _handle_execution_os_api(req)
        data = _json.loads(resp.body)
        assert "execution_os" in data

    def test_route_registered_in_build_app(self) -> None:
        from wallet_manager.metrics_server import MetricsServer
        server = MetricsServer.__new__(MetricsServer)
        app = server.build_app()
        routes = [r.resource.canonical for r in app.router.routes()]
        assert "/api/execution_os" in routes


# ---------------------------------------------------------------------------
# Bug-fix regression: _pending_twaps attribute name
# ---------------------------------------------------------------------------


class TestTWAPBugFix:
    def test_pending_twaps_attribute_exists(self) -> None:
        from wallet_manager.strategies.execution_quality import TWAPEmulator
        t = TWAPEmulator()
        assert hasattr(t, "_pending_twaps"), (
            "_pending_twaps attribute missing — was it renamed back to _pending_twaPs?"
        )

    def test_pending_twaps_camelcase_removed(self) -> None:
        from wallet_manager.strategies.execution_quality import TWAPEmulator
        t = TWAPEmulator()
        assert not hasattr(t, "_pending_twaPs"), (
            "_pending_twaPs still exists — old camelCase bug not fixed"
        )

    def test_start_twap_appends(self) -> None:
        from wallet_manager.strategies.execution_quality import TWAPEmulator
        t = TWAPEmulator()
        t.start_twap(2000.0)
        assert len(t._pending_twaps) == 1

    def test_update_prices_clears_completed(self) -> None:
        from wallet_manager.strategies.execution_quality import TWAPEmulator
        t = TWAPEmulator(slices=1, window_minutes=0.0)
        t.start_twap(2000.0)
        completed = t.update_prices(2010.0)
        assert isinstance(completed, list)


# ---------------------------------------------------------------------------
# Bug-fix regression: shortfall_tracker attribute name
# ---------------------------------------------------------------------------


class TestSORBugFix:
    def test_shortfall_tracker_attribute_exists(self) -> None:
        from wallet_manager.strategies.smart_order_router import SmartOrderRouter
        sor = SmartOrderRouter()
        assert hasattr(sor, "shortfall_tracker"), (
            "shortfall_tracker attribute missing — was it renamed back to is_tracker?"
        )

    def test_is_tracker_not_present(self) -> None:
        from wallet_manager.strategies.smart_order_router import SmartOrderRouter
        sor = SmartOrderRouter()
        assert not hasattr(sor, "is_tracker"), (
            "is_tracker still exists — old confusing name not removed"
        )

    def test_shortfall_tracker_is_correct_type(self) -> None:
        from wallet_manager.strategies.smart_order_router import (
            ExecutionShortfallTracker,
            SmartOrderRouter,
        )
        sor = SmartOrderRouter()
        assert isinstance(sor.shortfall_tracker, ExecutionShortfallTracker)

    def test_shortfall_tracker_record(self) -> None:
        from wallet_manager.strategies.smart_order_router import SmartOrderRouter
        sor = SmartOrderRouter()
        is_val = sor.shortfall_tracker.record(2000.0, 2010.0, "buy")
        assert abs(is_val - 0.005) < 1e-9
        assert sor.shortfall_tracker.trade_count == 1


# ---------------------------------------------------------------------------
# ExecutionShortfallTracker (existing module, deeper coverage)
# ---------------------------------------------------------------------------


class TestExecutionShortfallTracker:
    def test_empty_mean_is_zero(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        assert t.mean_is == 0.0

    def test_empty_median_is_zero(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        assert t.median_is == 0.0

    def test_buy_adverse_is_positive(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        val = t.record(2000.0, 2020.0, "buy")
        assert val > 0

    def test_sell_adverse_is_positive(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        val = t.record(2000.0, 1980.0, "sell")
        assert val > 0

    def test_window_limits_size(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        for i in range(60):
            t.record(float(1000 + i), float(1001 + i), "buy")
        assert t.trade_count == t.WINDOW

    def test_zero_arrival_returns_zero(self) -> None:
        from wallet_manager.strategies.smart_order_router import ExecutionShortfallTracker
        t = ExecutionShortfallTracker()
        val = t.record(0.0, 2000.0, "buy")
        assert val == 0.0
        assert t.trade_count == 0
