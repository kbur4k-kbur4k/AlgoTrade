"""
tests/unit/test_phase9_promotion_os.py

Phase 9 — Experiment and Promotion Operating System
=====================================================
Tests for:
  - ExperimentStage enum + _next_stage helper
  - PromotionGate dataclass
  - PromotionRecord dataclass
  - PromotionStore (SQLite persistence)
  - PromotionOS facade (register, evaluate, promote, demote, retire, scorecard)
  - Singleton accessor
  - /api/promotion_os handler
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# ExperimentStage + helpers
# ---------------------------------------------------------------------------


class TestExperimentStage:
    def test_values_exist(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        assert ExperimentStage.PAPER == "PAPER"
        assert ExperimentStage.SHADOW == "SHADOW"
        assert ExperimentStage.TINY_LIVE == "TINY_LIVE"
        assert ExperimentStage.SCALED_LIVE == "SCALED_LIVE"
        assert ExperimentStage.RETIRED == "RETIRED"

    def test_next_stage_paper(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, _next_stage
        assert _next_stage(ExperimentStage.PAPER) == ExperimentStage.SHADOW

    def test_next_stage_shadow(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, _next_stage
        assert _next_stage(ExperimentStage.SHADOW) == ExperimentStage.TINY_LIVE

    def test_next_stage_tiny_live(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, _next_stage
        assert _next_stage(ExperimentStage.TINY_LIVE) == ExperimentStage.SCALED_LIVE

    def test_next_stage_scaled_live_is_none(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, _next_stage
        assert _next_stage(ExperimentStage.SCALED_LIVE) is None

    def test_next_stage_retired_is_none(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, _next_stage
        assert _next_stage(ExperimentStage.RETIRED) is None


# ---------------------------------------------------------------------------
# PromotionGate
# ---------------------------------------------------------------------------


class TestPromotionGate:
    def test_defaults(self) -> None:
        from wallet_manager.promotion_os import PromotionGate
        g = PromotionGate()
        assert g.passed is False
        assert len(g.gate_id) == 36

    def test_to_dict_keys(self) -> None:
        from wallet_manager.promotion_os import PromotionGate
        g = PromotionGate(
            experiment_name="exp_a",
            metric_name="agreement_pct",
            threshold=60.0,
            actual_value=72.5,
            passed=True,
        )
        d = g.to_dict()
        assert d["passed"] is True
        assert d["actual_value"] == 72.5
        assert d["threshold"] == 60.0
        assert "gate_id" in d

    def test_unique_gate_ids(self) -> None:
        from wallet_manager.promotion_os import PromotionGate
        ids = {PromotionGate().gate_id for _ in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# PromotionRecord
# ---------------------------------------------------------------------------


class TestPromotionRecord:
    def test_defaults(self) -> None:
        from wallet_manager.promotion_os import ExperimentStage, PromotionRecord
        r = PromotionRecord()
        assert r.current_stage == ExperimentStage.PAPER
        assert r.promotion_count == 0
        assert r.demotion_count == 0

    def test_to_dict_round_trip(self) -> None:
        from wallet_manager.promotion_os import PromotionRecord
        r = PromotionRecord(
            experiment_name="exp_test",
            promotion_count=2,
            demotion_count=1,
        )
        d = r.to_dict()
        assert d["experiment_name"] == "exp_test"
        assert d["promotion_count"] == 2
        assert d["gates_passed"] == []
        assert d["gates_failed"] == []


# ---------------------------------------------------------------------------
# PromotionStore
# ---------------------------------------------------------------------------


class TestPromotionStore:
    def _make_store(self, tmp_path: Path):
        from wallet_manager.promotion_os import PromotionStore
        return PromotionStore(db_path=tmp_path / "promo_test.db")

    def test_tables_created(self, tmp_path: Path) -> None:
        import sqlite3
        self._make_store(tmp_path)
        db_path = tmp_path / "promo_test.db"
        with sqlite3.connect(db_path) as conn:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        assert "promotion_records" in names
        assert "promotion_gates" in names

    def test_save_and_load_record(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionRecord, PromotionStore
        store = PromotionStore(db_path=tmp_path / "promo_test.db")
        r = PromotionRecord(experiment_name="exp_alpha", promotion_count=1)
        ok = store.save_record(r)
        assert ok is True
        loaded = store.load_record("exp_alpha")
        assert loaded is not None
        assert loaded.experiment_name == "exp_alpha"
        assert loaded.promotion_count == 1

    def test_load_record_missing_returns_none(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        assert store.load_record("nonexistent") is None

    def test_save_and_load_gate(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionGate, PromotionStore
        store = PromotionStore(db_path=tmp_path / "promo_test.db")
        g = PromotionGate(
            experiment_name="exp_alpha",
            metric_name="min_cycles",
            threshold=50.0,
            actual_value=75.0,
            passed=True,
        )
        ok = store.save_gate(g)
        assert ok is True
        gates = store.get_gates("exp_alpha")
        assert len(gates) == 1
        assert gates[0]["metric_name"] == "min_cycles"

    def test_list_experiments(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionRecord, PromotionStore
        store = PromotionStore(db_path=tmp_path / "promo_test.db")
        store.save_record(PromotionRecord(experiment_name="exp_1"))
        store.save_record(PromotionRecord(experiment_name="exp_2"))
        exps = store.list_experiments()
        names = [e["experiment_name"] for e in exps]
        assert "exp_1" in names
        assert "exp_2" in names

    def test_count_experiments(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionRecord, PromotionStore
        store = PromotionStore(db_path=tmp_path / "promo_test.db")
        assert store.count_experiments() == 0
        store.save_record(PromotionRecord(experiment_name="exp_x"))
        assert store.count_experiments() == 1

    def test_upsert_updates_stage(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage, PromotionRecord, PromotionStore
        store = PromotionStore(db_path=tmp_path / "promo_test.db")
        r = PromotionRecord(experiment_name="exp_z", current_stage=ExperimentStage.PAPER)
        store.save_record(r)
        r.current_stage = ExperimentStage.SHADOW
        store.save_record(r)
        loaded = store.load_record("exp_z")
        assert loaded is not None
        assert loaded.current_stage == ExperimentStage.SHADOW


# ---------------------------------------------------------------------------
# PromotionOS facade
# ---------------------------------------------------------------------------


class TestPromotionOS:
    def _make_pos(self, tmp_path: Path):
        from wallet_manager.promotion_os import PromotionOS
        return PromotionOS(db_path=tmp_path / "pos_test.db")

    def test_register_creates_record_at_paper(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        rec = pos.register("exp_register")
        assert rec.current_stage == ExperimentStage.PAPER
        assert rec.experiment_name == "exp_register"

    def test_register_idempotent(self, tmp_path: Path) -> None:
        pos = self._make_pos(tmp_path)
        r1 = pos.register("exp_idem")
        r2 = pos.register("exp_idem")
        assert r1.record_id == r2.record_id

    def test_evaluate_promotion_paper_to_shadow(self, tmp_path: Path) -> None:
        pos = self._make_pos(tmp_path)
        pos.register("exp_eval")
        gates = pos.evaluate_promotion(
            "exp_eval",
            {"min_cycles": 60.0, "agreement_pct": 65.0},
        )
        assert len(gates) == 2
        assert all(g.passed for g in gates)

    def test_evaluate_promotion_fails_low_cycles(self, tmp_path: Path) -> None:
        pos = self._make_pos(tmp_path)
        pos.register("exp_fail")
        gates = pos.evaluate_promotion(
            "exp_fail",
            {"min_cycles": 10.0, "agreement_pct": 70.0},
        )
        assert any(not g.passed for g in gates)

    def test_promote_advances_stage_when_gates_pass(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_promo")
        promoted, reason, rec = pos.promote(
            "exp_promo",
            {"min_cycles": 100.0, "agreement_pct": 75.0},
        )
        assert promoted is True
        assert rec.current_stage == ExperimentStage.SHADOW
        assert "Promoted" in reason
        assert rec.promotion_count == 1

    def test_promote_blocked_when_gate_fails(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_block")
        promoted, reason, rec = pos.promote(
            "exp_block",
            {"min_cycles": 1.0, "agreement_pct": 10.0},
        )
        assert promoted is False
        assert rec.current_stage == ExperimentStage.PAPER
        assert "blocked" in reason.lower()

    def test_demote_reverts_stage(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_demote")
        pos.promote("exp_demote", {"min_cycles": 100.0, "agreement_pct": 80.0})
        rec = pos.demote("exp_demote", reason="Test rollback")
        assert rec.current_stage == ExperimentStage.PAPER
        assert rec.demotion_count == 1

    def test_demote_at_paper_stays_paper(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_stay")
        rec = pos.demote("exp_stay")
        assert rec.current_stage == ExperimentStage.PAPER

    def test_retire_sets_retired_stage(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_retire")
        rec = pos.retire("exp_retire", reason="Alpha decayed")
        assert rec.current_stage == ExperimentStage.RETIRED

    def test_multi_stage_promotion_chain(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import ExperimentStage
        pos = self._make_pos(tmp_path)
        pos.register("exp_chain")
        # Paper → Shadow
        pos.promote("exp_chain", {"min_cycles": 100.0, "agreement_pct": 80.0})
        # Shadow → Tiny Live
        pos.promote("exp_chain", {
            "min_cycles": 150.0, "shared_realized_pnl": 2.0, "agreement_pct": 70.0
        })
        rec = pos._store.load_record("exp_chain")
        assert rec is not None
        assert rec.current_stage == ExperimentStage.TINY_LIVE
        assert rec.promotion_count == 2


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


class TestPromotionOSScorecard:
    def test_scorecard_keys(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionOS
        pos = PromotionOS(db_path=tmp_path / "scorecard.db")
        sc = pos.get_scorecard()
        assert "generated_at" in sc
        assert "phase" in sc
        assert sc["phase"] == 9
        assert "total_experiments" in sc
        assert "stage_counts" in sc
        assert "experiments" in sc

    def test_scorecard_empty(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionOS
        pos = PromotionOS(db_path=tmp_path / "scorecard.db")
        sc = pos.get_scorecard()
        assert sc["total_experiments"] == 0

    def test_scorecard_populated(self, tmp_path: Path) -> None:
        from wallet_manager.promotion_os import PromotionOS
        pos = PromotionOS(db_path=tmp_path / "scorecard.db")
        pos.register("sc_exp")
        sc = pos.get_scorecard()
        assert sc["total_experiments"] == 1
        assert "PAPER" in sc["stage_counts"]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestPromotionOSSingleton:
    def test_singleton(self, tmp_path: Path) -> None:
        import wallet_manager.promotion_os as pos_mod
        old = pos_mod._promotion_os_instance
        pos_mod._promotion_os_instance = None
        try:
            from wallet_manager.promotion_os import get_promotion_os
            a = get_promotion_os(db_path=tmp_path / "singleton.db")
            b = get_promotion_os(db_path=tmp_path / "singleton.db")
            assert a is b
        finally:
            pos_mod._promotion_os_instance = old


# ---------------------------------------------------------------------------
# /api/promotion_os handler
# ---------------------------------------------------------------------------


class TestPromotionOsApiHandler:
    @pytest.mark.asyncio
    async def test_handler_returns_status_ok(self) -> None:
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_promotion_os_api
        req = MagicMock()
        resp = await _handle_promotion_os_api(req)
        data = _json.loads(resp.body)
        assert data["status"] == "ok"
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_handler_includes_promotion_os_key(self) -> None:
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_promotion_os_api
        req = MagicMock()
        resp = await _handle_promotion_os_api(req)
        data = _json.loads(resp.body)
        assert "promotion_os" in data

    def test_route_registered_in_build_app(self) -> None:
        from wallet_manager.metrics_server import MetricsServer
        server = MetricsServer.__new__(MetricsServer)
        app = server.build_app()
        routes = [r.resource.canonical for r in app.router.routes()]
        assert "/api/promotion_os" in routes
