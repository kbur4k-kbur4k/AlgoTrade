"""
tests/unit/test_phase7_risk_os.py

Phase 7 — Risk Operating System tests.

Covers:
- RiskLevel classification (_classify_risk_level)
- Composite score calculation (_compute_composite_score)
- Veto narrative construction (_build_veto_narrative)
- RiskStateSnapshot creation and serialization
- RiskStateStore: write, query recent, trajectory, count
- RiskOS.evaluate_and_record (mocked paper_engine and committee)
- /api/risk_state metrics endpoint
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wallet_manager.risk_os import (
    RiskLevel,
    RiskOS,
    RiskStateSnapshot,
    RiskStateStore,
    _build_veto_narrative,
    _classify_risk_level,
    _compute_composite_score,
    get_risk_os,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_snapshot(
    risk_level: RiskLevel = RiskLevel.GREEN,
    composite_score: int = 10,
    blocking: list[str] | None = None,
    reducing: list[str] | None = None,
    drawdown_pct: float = 0.0,
    drawdown_state: str = "normal",
    var_99_pct: float = 0.005,
    regime: str = "low_vol",
    kelly: float = 1.0,
) -> RiskStateSnapshot:
    blocking = blocking or []
    reducing = reducing or []
    return RiskStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id="test_session",
        timestamp=time.time(),
        risk_level=risk_level,
        composite_score=composite_score,
        committee_verdict={"allowed": not blocking, "risk_score": composite_score},
        blocking_brakes=blocking,
        reducing_brakes=reducing,
        drawdown_pct=drawdown_pct,
        drawdown_state=drawdown_state,
        var_99_pct=var_99_pct,
        regime_label=regime,
        kelly_multiplier=kelly,
        veto_narrative=f"[{risk_level}] test",
    )


# ---------------------------------------------------------------------------
# RiskLevel classification
# ---------------------------------------------------------------------------


def test_classify_green_no_brakes():
    level = _classify_risk_level([], [], composite_score=0)
    assert level == RiskLevel.GREEN


def test_classify_green_low_score():
    level = _classify_risk_level([], [], composite_score=29)
    assert level == RiskLevel.GREEN


def test_classify_yellow_one_reduce():
    level = _classify_risk_level([], ["ModelDisagreement"], composite_score=10)
    assert level == RiskLevel.YELLOW


def test_classify_yellow_score_30():
    level = _classify_risk_level([], [], composite_score=30)
    assert level == RiskLevel.YELLOW


def test_classify_orange_two_reduces():
    level = _classify_risk_level([], ["ModelDisagreement", "HighSpread"], composite_score=25)
    assert level == RiskLevel.ORANGE


def test_classify_orange_score_60():
    level = _classify_risk_level([], [], composite_score=60)
    assert level == RiskLevel.ORANGE


def test_classify_red_one_blocking():
    level = _classify_risk_level(["DailyLossLimit"], [], composite_score=25)
    assert level == RiskLevel.RED


def test_classify_red_multiple_blocking():
    level = _classify_risk_level(["DailyLossLimit", "SessionKillSwitch"], [], composite_score=75)
    assert level == RiskLevel.RED


def test_classify_red_overrides_score():
    level = _classify_risk_level(["DailyLossLimit"], [], composite_score=5)
    assert level == RiskLevel.RED


# ---------------------------------------------------------------------------
# Composite score calculation
# ---------------------------------------------------------------------------


def test_composite_score_clean():
    score = _compute_composite_score([], [], drawdown_pct=0.0, var_99_pct=0.005)
    assert score == 0


def test_composite_score_one_blocking():
    score = _compute_composite_score(["DailyLossLimit"], [], drawdown_pct=0.0, var_99_pct=0.0)
    assert score == 25


def test_composite_score_three_blocking_capped():
    score = _compute_composite_score(
        ["A", "B", "C", "D"], [], drawdown_pct=0.0, var_99_pct=0.0
    )
    assert score == 75  # min(75, 4*25)=75 — blocking contribution capped at 75


def test_composite_score_reducing():
    score = _compute_composite_score([], ["ModelDisagreement"], drawdown_pct=0.0, var_99_pct=0.0)
    assert score == 10


def test_composite_score_three_reducing_capped():
    score = _compute_composite_score(
        [], ["A", "B", "C", "D"], drawdown_pct=0.0, var_99_pct=0.0
    )
    assert score == 30  # capped at 30


def test_composite_score_drawdown_5_to_10():
    score = _compute_composite_score([], [], drawdown_pct=0.07, var_99_pct=0.0)
    assert score == 15


def test_composite_score_drawdown_above_10():
    score = _compute_composite_score([], [], drawdown_pct=0.12, var_99_pct=0.0)
    assert score == 25


def test_composite_score_var_alert():
    score = _compute_composite_score([], [], drawdown_pct=0.0, var_99_pct=0.03)
    assert score == 10


def test_composite_score_combined():
    score = _compute_composite_score(
        ["DailyLossLimit"],
        ["ModelDisagreement"],
        drawdown_pct=0.07,
        var_99_pct=0.03,
    )
    assert score == min(100, 25 + 10 + 15 + 10)


def test_composite_score_max_100():
    score = _compute_composite_score(
        ["A", "B", "C"],
        ["D", "E", "F"],
        drawdown_pct=0.15,
        var_99_pct=0.05,
    )
    assert score == 100


# ---------------------------------------------------------------------------
# Veto narrative
# ---------------------------------------------------------------------------


def test_veto_narrative_all_clear():
    narrative = _build_veto_narrative(
        [], [], RiskLevel.GREEN, 0, 0.0, 0.0, "low_vol", 1.0
    )
    assert "GREEN" in narrative
    assert "all_clear" in narrative


def test_veto_narrative_blocked():
    narrative = _build_veto_narrative(
        ["DailyLossLimit"], [], RiskLevel.RED, 25, 0.02, 0.01, "high_vol", 0.5
    )
    assert "BLOCKED_BY=DailyLossLimit" in narrative
    assert "RED" in narrative


def test_veto_narrative_reduce():
    narrative = _build_veto_narrative(
        [], ["HighSpread"], RiskLevel.YELLOW, 10, 0.01, 0.005, "normal", 0.75
    )
    assert "REDUCE_BY=HighSpread" in narrative
    assert "YELLOW" in narrative


def test_veto_narrative_contains_regime():
    narrative = _build_veto_narrative(
        [], [], RiskLevel.GREEN, 0, 0.0, 0.0, "crisis", 0.25
    )
    assert "regime=crisis" in narrative


def test_veto_narrative_contains_kelly():
    narrative = _build_veto_narrative(
        [], [], RiskLevel.GREEN, 0, 0.0, 0.0, "low_vol", 0.75
    )
    assert "kelly_mult=0.750" in narrative


# ---------------------------------------------------------------------------
# RiskStateSnapshot
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_keys():
    snap = _make_snapshot(RiskLevel.GREEN, 5)
    d = snap.to_dict()
    required = {
        "snapshot_id", "session_id", "timestamp", "risk_level", "composite_score",
        "committee_verdict", "blocking_brakes", "reducing_brakes", "drawdown_pct",
        "drawdown_state", "var_99_pct", "regime_label", "kelly_multiplier",
        "veto_narrative", "extra",
    }
    assert required.issubset(d.keys())


def test_snapshot_risk_level_serialized_as_string():
    snap = _make_snapshot(RiskLevel.RED, 75, blocking=["DailyLossLimit"])
    d = snap.to_dict()
    assert d["risk_level"] == "RED"


def test_snapshot_drawdown_pct_rounded():
    snap = _make_snapshot(drawdown_pct=0.123456789)
    d = snap.to_dict()
    assert isinstance(d["drawdown_pct"], float)


# ---------------------------------------------------------------------------
# RiskStateStore
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path):
    db = tmp_path / "test_risk_os.db"
    return RiskStateStore(db_path=db)


def test_store_record_and_count(tmp_store):
    snap = _make_snapshot(RiskLevel.GREEN, 5)
    tmp_store.record(snap)
    assert tmp_store.count() == 1


def test_store_record_idempotent(tmp_store):
    snap = _make_snapshot(RiskLevel.GREEN, 5)
    tmp_store.record(snap)
    tmp_store.record(snap)  # same snapshot_id — should be ignored
    assert tmp_store.count() == 1


def test_store_get_recent_empty(tmp_store):
    result = tmp_store.get_recent(10)
    assert result == []


def test_store_get_recent_returns_newest_first(tmp_store):
    for i in range(5):
        snap = _make_snapshot(composite_score=i * 10)
        snap = RiskStateSnapshot(
            snapshot_id=str(uuid.uuid4()),
            session_id="s",
            timestamp=time.time() + i,
            risk_level=RiskLevel.GREEN,
            composite_score=i * 10,
            committee_verdict={},
            blocking_brakes=[],
            reducing_brakes=[],
            drawdown_pct=0.0,
            drawdown_state="normal",
            var_99_pct=0.0,
            regime_label="low_vol",
            kelly_multiplier=1.0,
            veto_narrative="",
        )
        tmp_store.record(snap)
    recent = tmp_store.get_recent(3)
    assert len(recent) == 3
    assert recent[0]["composite_score"] >= recent[1]["composite_score"]


def test_store_get_recent_limit(tmp_store):
    for _ in range(10):
        snap = _make_snapshot()
        snap = RiskStateSnapshot(
            snapshot_id=str(uuid.uuid4()),
            session_id="s",
            timestamp=time.time(),
            risk_level=RiskLevel.GREEN,
            composite_score=0,
            committee_verdict={},
            blocking_brakes=[],
            reducing_brakes=[],
            drawdown_pct=0.0,
            drawdown_state="normal",
            var_99_pct=0.0,
            regime_label="low_vol",
            kelly_multiplier=1.0,
            veto_narrative="",
        )
        tmp_store.record(snap)
    result = tmp_store.get_recent(5)
    assert len(result) == 5


def test_store_trajectory_empty(tmp_store):
    traj = tmp_store.get_risk_trajectory(24)
    assert traj == []


def test_store_trajectory_includes_recent(tmp_store):
    snap = RiskStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id="s",
        timestamp=time.time(),
        risk_level=RiskLevel.YELLOW,
        composite_score=35,
        committee_verdict={},
        blocking_brakes=[],
        reducing_brakes=["ModelDisagreement"],
        drawdown_pct=0.02,
        drawdown_state="normal",
        var_99_pct=0.01,
        regime_label="normal",
        kelly_multiplier=0.75,
        veto_narrative="",
    )
    tmp_store.record(snap)
    traj = tmp_store.get_risk_trajectory(24)
    assert len(traj) == 1
    assert traj[0]["risk_level"] == "YELLOW"


def test_store_trajectory_excludes_old(tmp_store):
    old_snap = RiskStateSnapshot(
        snapshot_id=str(uuid.uuid4()),
        session_id="s",
        timestamp=time.time() - 48 * 3600,  # 48 hours ago
        risk_level=RiskLevel.RED,
        composite_score=75,
        committee_verdict={},
        blocking_brakes=["DailyLossLimit"],
        reducing_brakes=[],
        drawdown_pct=0.12,
        drawdown_state="halted",
        var_99_pct=0.03,
        regime_label="crisis",
        kelly_multiplier=0.0,
        veto_narrative="",
    )
    tmp_store.record(old_snap)
    traj = tmp_store.get_risk_trajectory(24)
    assert len(traj) == 0


def test_store_recent_row_structure(tmp_store):
    snap = _make_snapshot(RiskLevel.ORANGE, 65, reducing=["A", "B"])
    tmp_store.record(snap)
    recent = tmp_store.get_recent(1)
    row = recent[0]
    assert "snapshot_id" in row
    assert "risk_level" in row
    assert "composite_score" in row
    assert "blocking_brakes" in row
    assert "reducing_brakes" in row
    assert isinstance(row["blocking_brakes"], list)
    assert isinstance(row["reducing_brakes"], list)


# ---------------------------------------------------------------------------
# RiskOS.evaluate_and_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_os_evaluate_and_record_no_engine(tmp_path):
    db = tmp_path / "risk_os_test.db"
    ros = RiskOS(db_path=db)
    snapshot = await ros.evaluate_and_record(
        paper_engine=None,
        confidence=0.6,
        regime_label="low_vol",
        equity_usd=10_000.0,
        session_id="test_session",
    )
    assert isinstance(snapshot, RiskStateSnapshot)
    assert snapshot.risk_level in RiskLevel.__members__.values()
    assert snapshot.composite_score >= 0
    assert snapshot.session_id == "test_session"
    assert snapshot.regime_label == "low_vol"


@pytest.mark.asyncio
async def test_risk_os_persists_snapshot(tmp_path):
    db = tmp_path / "risk_os_persist.db"
    ros = RiskOS(db_path=db)
    await ros.evaluate_and_record(paper_engine=None)
    assert ros.get_store().count() == 1


@pytest.mark.asyncio
async def test_risk_os_last_snapshot_set(tmp_path):
    db = tmp_path / "risk_os_last.db"
    ros = RiskOS(db_path=db)
    assert ros._last_snapshot is None
    await ros.evaluate_and_record(paper_engine=None)
    assert ros._last_snapshot is not None


@pytest.mark.asyncio
async def test_risk_os_to_dict_structure(tmp_path):
    db = tmp_path / "risk_os_dict.db"
    ros = RiskOS(db_path=db)
    await ros.evaluate_and_record(paper_engine=None, session_id="s1")
    d = ros.to_dict()
    assert "last_snapshot" in d
    assert "recent_snapshots" in d
    assert "trajectory_24h" in d
    assert "total_snapshots" in d
    assert d["total_snapshots"] == 1


@pytest.mark.asyncio
async def test_risk_os_green_on_clean_state(tmp_path):
    db = tmp_path / "risk_os_green.db"
    ros = RiskOS(db_path=db)
    with (
        patch("wallet_manager.risk_committee.get_paper_risk_committee") as mock_committee,
        patch("wallet_manager.risk_intelligence.get_risk_intelligence"),
        patch("wallet_manager.strategies.deep_kelly_risk.get_deep_kelly_engine"),
    ):
        mock_verdict = MagicMock()
        mock_verdict.to_dict.return_value = {"allowed": True, "risk_score": 0}
        mock_verdict.blocking_brakes = []
        mock_verdict.brake_results = []
        mock_committee.return_value.evaluate = AsyncMock(return_value=mock_verdict)
        snapshot = await ros.evaluate_and_record(paper_engine=None)
    assert snapshot.risk_level == RiskLevel.GREEN


@pytest.mark.asyncio
async def test_risk_os_red_on_blocking_brake(tmp_path):
    db = tmp_path / "risk_os_red.db"
    ros = RiskOS(db_path=db)
    with (
        patch("wallet_manager.risk_committee.get_paper_risk_committee") as mock_committee,
        patch("wallet_manager.risk_intelligence.get_risk_intelligence"),
        patch("wallet_manager.strategies.deep_kelly_risk.get_deep_kelly_engine"),
    ):
        mock_verdict = MagicMock()
        mock_verdict.to_dict.return_value = {"allowed": False, "risk_score": 25}
        mock_verdict.blocking_brakes = ["DailyLossLimit"]
        mock_verdict.brake_results = []
        mock_committee.return_value.evaluate = AsyncMock(return_value=mock_verdict)
        snapshot = await ros.evaluate_and_record(paper_engine=None)
    assert snapshot.risk_level == RiskLevel.RED
    assert "DailyLossLimit" in snapshot.blocking_brakes


# ---------------------------------------------------------------------------
# /api/risk_state endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_risk_state_endpoint(tmp_path):
    import aiohttp.web

    from wallet_manager.metrics_server import _handle_risk_state_api

    db = tmp_path / "risk_os_api.db"
    ros = RiskOS(db_path=db)

    with patch("wallet_manager.risk_os.get_risk_os", return_value=ros):
        with patch("wallet_manager.strategies.paper_engine._engine_instance", None):
            request = MagicMock()
            response = await _handle_risk_state_api(request)
            assert response.status == 200
            body = json.loads(response.body)
            assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# get_risk_os singleton
# ---------------------------------------------------------------------------


def test_get_risk_os_singleton(tmp_path):
    import wallet_manager.risk_os as ros_module
    original = ros_module._risk_os
    try:
        ros_module._risk_os = None
        with patch("wallet_manager.risk_os.RiskStateStore"):
            a = get_risk_os()
            b = get_risk_os()
            assert a is b
    finally:
        ros_module._risk_os = original
