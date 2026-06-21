"""
tests/unit/test_phase10_learning_os.py

Phase 10 — Continuous Learning Operating System
=================================================
Tests for:
  - LearningCycle dataclass
  - LearningCycleStore (SQLite persistence)
  - LearningOS facade (run_cycle, get_scorecard)
  - Singleton accessor
  - /api/learning_os handler
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# LearningCycle
# ---------------------------------------------------------------------------


class TestLearningCycle:
    def test_defaults(self) -> None:
        from wallet_manager.learning_os import LearningCycle
        c = LearningCycle()
        assert c.drift_level == "UNKNOWN"
        assert c.drift_trend == "stable"
        assert c.drift_alert is False
        assert c.setup_decay_count == 0
        assert len(c.cycle_id) == 36

    def test_to_dict_keys(self) -> None:
        from wallet_manager.learning_os import LearningCycle
        c = LearningCycle(
            drift_level="MILD",
            drift_trend="increasing",
            drift_alert=True,
            setup_decay_count=2,
            feature_alert_count=1,
            suggestions_count=3,
            alerts=["alert_a", "alert_b"],
        )
        d = c.to_dict()
        assert d["drift_level"] == "MILD"
        assert d["drift_alert"] is True
        assert d["setup_decay_count"] == 2
        assert d["suggestions_count"] == 3
        assert len(d["alerts"]) == 2
        assert "cycle_id" in d
        assert "timestamp" in d

    def test_unique_cycle_ids(self) -> None:
        from wallet_manager.learning_os import LearningCycle
        ids = {LearningCycle().cycle_id for _ in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# LearningCycleStore
# ---------------------------------------------------------------------------


class TestLearningCycleStore:
    def _make_store(self, tmp_path: Path):
        from wallet_manager.learning_os import LearningCycleStore
        return LearningCycleStore(db_path=tmp_path / "learning_test.db")

    def test_table_created(self, tmp_path: Path) -> None:
        import sqlite3
        self._make_store(tmp_path)
        with sqlite3.connect(tmp_path / "learning_test.db") as conn:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
        assert "learning_cycles" in names

    def test_save_and_get_recent(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningCycleStore
        store = LearningCycleStore(db_path=tmp_path / "learning_test.db")
        c = LearningCycle(drift_level="MILD", setup_decay_count=1)
        ok = store.save(c)
        assert ok is True
        recent = store.get_recent(5)
        assert len(recent) == 1
        assert recent[0]["drift_level"] == "MILD"

    def test_get_recent_newest_first(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningCycleStore
        store = LearningCycleStore(db_path=tmp_path / "learning_test.db")
        for i in range(5):
            store.save(LearningCycle(timestamp=float(i), drift_level="NOMINAL"))
        recent = store.get_recent(5)
        assert recent[0]["timestamp"] >= recent[-1]["timestamp"]

    def test_get_stats_empty(self, tmp_path: Path) -> None:
        store = self._make_store(tmp_path)
        stats = store.get_stats()
        assert stats["total_cycles"] == 0

    def test_get_stats_populated(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningCycleStore
        store = LearningCycleStore(db_path=tmp_path / "learning_test.db")
        store.save(LearningCycle(
            drift_alert=True, setup_decay_count=2,
            feature_alert_count=1, suggestions_count=3,
        ))
        store.save(LearningCycle(
            drift_alert=False, setup_decay_count=0,
            feature_alert_count=0, suggestions_count=1,
        ))
        stats = store.get_stats()
        assert stats["total_cycles"] == 2
        assert stats["total_drift_alerts"] == 1
        assert abs(stats["avg_decay_count"] - 1.0) < 0.01
        assert abs(stats["avg_suggestions"] - 2.0) < 0.01

    def test_count(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningCycleStore
        store = LearningCycleStore(db_path=tmp_path / "learning_test.db")
        assert store.count() == 0
        store.save(LearningCycle())
        assert store.count() == 1

    def test_limit_respected(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningCycleStore
        store = LearningCycleStore(db_path=tmp_path / "learning_test.db")
        for _ in range(10):
            store.save(LearningCycle())
        assert len(store.get_recent(3)) == 3


# ---------------------------------------------------------------------------
# LearningOS facade
# ---------------------------------------------------------------------------


class TestLearningOS:
    def _make_los(self, tmp_path: Path):
        from wallet_manager.learning_os import LearningOS
        return LearningOS(db_path=tmp_path / "los_test.db")

    @pytest.mark.asyncio
    async def test_run_cycle_returns_learning_cycle(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningCycle, LearningOS
        los = LearningOS(db_path=tmp_path / "los_test.db")

        mock_report = {
            "drift": {"recent_level": "MILD", "trend": "increasing", "alert": False},
            "setup_decay": {"decaying": [{"setup_tag": "a"}], "stable": []},
            "threshold_suggestions": [{"suggestion": "relax alpha"}],
            "feature_drift": {"total_alerts": 1},
            "alerts": ["drift alert: MILD"],
        }

        with patch(
            "wallet_manager.continuous_learning.get_continuous_learner"
        ) as mock_get:
            mock_learner = MagicMock()
            mock_learner.generate_learning_report = AsyncMock(return_value=mock_report)
            mock_get.return_value = mock_learner

            cycle = await los.run_cycle(paper_engine=None)

        assert isinstance(cycle, LearningCycle)
        assert cycle.drift_level == "MILD"
        assert cycle.drift_trend == "increasing"
        assert cycle.setup_decay_count == 1
        assert cycle.suggestions_count == 1
        assert cycle.feature_alert_count == 1

    @pytest.mark.asyncio
    async def test_run_cycle_persists_to_store(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS

        los = LearningOS(db_path=tmp_path / "los_test.db")
        mock_report = {
            "drift": {"recent_level": "NOMINAL", "trend": "stable", "alert": False},
            "setup_decay": {"decaying": [], "stable": []},
            "threshold_suggestions": [],
            "feature_drift": {"total_alerts": 0},
            "alerts": [],
        }

        with patch("wallet_manager.continuous_learning.get_continuous_learner") as mock_get:
            mock_learner = MagicMock()
            mock_learner.generate_learning_report = AsyncMock(return_value=mock_report)
            mock_get.return_value = mock_learner

            await los.run_cycle()

        assert los._store.count() == 1

    @pytest.mark.asyncio
    async def test_run_cycle_drift_alert_flag(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS

        los = LearningOS(db_path=tmp_path / "los_test.db")
        mock_report = {
            "drift": {"recent_level": "SEVERE", "trend": "increasing", "alert": True},
            "setup_decay": {"decaying": [], "stable": []},
            "threshold_suggestions": [],
            "feature_drift": {"total_alerts": 0},
            "alerts": ["Drift alert: SEVERE"],
        }

        with patch("wallet_manager.continuous_learning.get_continuous_learner") as mock_get:
            mock_learner = MagicMock()
            mock_learner.generate_learning_report = AsyncMock(return_value=mock_report)
            mock_get.return_value = mock_learner

            cycle = await los.run_cycle()

        assert cycle.drift_alert is True

    @pytest.mark.asyncio
    async def test_alerts_capped_at_20(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS

        los = LearningOS(db_path=tmp_path / "los_test.db")
        mock_report = {
            "drift": {"recent_level": "NOMINAL", "trend": "stable", "alert": False},
            "setup_decay": {"decaying": [], "stable": []},
            "threshold_suggestions": [],
            "feature_drift": {"total_alerts": 0},
            "alerts": [f"alert_{i}" for i in range(30)],
        }

        with patch("wallet_manager.continuous_learning.get_continuous_learner") as mock_get:
            mock_learner = MagicMock()
            mock_learner.generate_learning_report = AsyncMock(return_value=mock_report)
            mock_get.return_value = mock_learner

            cycle = await los.run_cycle()

        assert len(cycle.alerts) <= 20


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------


class TestLearningOSScorecard:
    def test_scorecard_keys(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS
        los = LearningOS(db_path=tmp_path / "sc_test.db")
        sc = los.get_scorecard()
        assert "generated_at" in sc
        assert "phase" in sc
        assert sc["phase"] == 10
        assert "store_stats" in sc
        assert "recent_cycles" in sc

    def test_scorecard_empty(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS
        los = LearningOS(db_path=tmp_path / "sc_test.db")
        sc = los.get_scorecard()
        assert sc["store_stats"]["total_cycles"] == 0

    def test_scorecard_generated_at_recent(self, tmp_path: Path) -> None:
        from wallet_manager.learning_os import LearningOS
        los = LearningOS(db_path=tmp_path / "sc_test.db")
        sc = los.get_scorecard()
        assert abs(sc["generated_at"] - time.time()) < 5.0


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestLearningOSSingleton:
    def test_singleton(self, tmp_path: Path) -> None:
        import wallet_manager.learning_os as los_mod
        old = los_mod._learning_os_instance
        los_mod._learning_os_instance = None
        try:
            from wallet_manager.learning_os import get_learning_os
            a = get_learning_os(db_path=tmp_path / "singleton.db")
            b = get_learning_os(db_path=tmp_path / "singleton.db")
            assert a is b
        finally:
            los_mod._learning_os_instance = old


# ---------------------------------------------------------------------------
# /api/learning_os handler
# ---------------------------------------------------------------------------


class TestLearningOsApiHandler:
    @pytest.mark.asyncio
    async def test_handler_returns_status_ok(self) -> None:
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_learning_os_api
        req = MagicMock()
        resp = await _handle_learning_os_api(req)
        data = _json.loads(resp.body)
        assert data["status"] == "ok"
        assert "generated_at" in data

    @pytest.mark.asyncio
    async def test_handler_includes_learning_os_key(self) -> None:
        import json as _json
        from unittest.mock import MagicMock

        from wallet_manager.metrics_server import _handle_learning_os_api
        req = MagicMock()
        resp = await _handle_learning_os_api(req)
        data = _json.loads(resp.body)
        assert "learning_os" in data

    def test_route_registered_in_build_app(self) -> None:
        from wallet_manager.metrics_server import MetricsServer
        server = MetricsServer.__new__(MetricsServer)
        app = server.build_app()
        routes = [r.resource.canonical for r in app.router.routes()]
        assert "/api/learning_os" in routes
