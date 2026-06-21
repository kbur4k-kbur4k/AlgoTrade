"""
wallet_manager/risk_os.py

Phase 7 — Risk Operating System
=================================
Unifies all risk components (RiskCommittee, RiskIntelligence, DeepKelly)
into a single, auditable, persistable Risk OS layer.

Design:
- RiskLevel        : GREEN / YELLOW / ORANGE / RED classification
- RiskStateSnapshot: Unified snapshot combining committee + intelligence
- RiskStateStore   : Persists snapshots to quant_analytics.db for audit
- RiskOS           : Facade that evaluates and records in one call
- get_risk_os()    : Singleton accessor

Exit gate (roadmap §13.7):
  Risk can be reasoned about as a system, not as scattered conditionals.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)


# ---------------------------------------------------------------------------
# Risk Level
# ---------------------------------------------------------------------------


class RiskLevel(StrEnum):
    GREEN = "GREEN"    # No active brakes, composite score < 30
    YELLOW = "YELLOW"  # REDUCE verdicts or score 30-59
    ORANGE = "ORANGE"  # Multiple REDUCE or score 60-79
    RED = "RED"        # At least one BLOCK brake active


def _classify_risk_level(
    blocking_brakes: list[str],
    reducing_brakes: list[str],
    composite_score: int,
) -> RiskLevel:
    if blocking_brakes:
        return RiskLevel.RED
    if len(reducing_brakes) >= 2 or composite_score >= 60:
        return RiskLevel.ORANGE
    if reducing_brakes or composite_score >= 30:
        return RiskLevel.YELLOW
    return RiskLevel.GREEN


def _compute_composite_score(
    blocking_brakes: list[str],
    reducing_brakes: list[str],
    drawdown_pct: float,
    var_99_pct: float,
) -> int:
    """Compute composite risk score 0-100.

    Contributions:
    - Each blocking brake  : +25 (capped at 75)
    - Each reducing brake  : +10 (capped at 30)
    - Drawdown > 5%        : +15
    - Drawdown > 10%       : +25 (additive)
    - VaR99 > 2%           : +10
    """
    score = 0
    score += min(75, len(blocking_brakes) * 25)
    score += min(30, len(reducing_brakes) * 10)
    if drawdown_pct > 0.10:
        score += 25
    elif drawdown_pct > 0.05:
        score += 15
    if var_99_pct > 0.02:
        score += 10
    return min(100, score)


def _build_veto_narrative(
    blocking_brakes: list[str],
    reducing_brakes: list[str],
    risk_level: RiskLevel,
    composite_score: int,
    drawdown_pct: float,
    var_99_pct: float,
    regime_label: str,
    kelly_multiplier: float,
) -> str:
    """Build a structured, human-readable veto narrative."""
    parts: list[str] = [f"[{risk_level}] composite={composite_score}/100"]
    if blocking_brakes:
        parts.append(f"BLOCKED_BY={','.join(blocking_brakes)}")
    if reducing_brakes:
        parts.append(f"REDUCE_BY={','.join(reducing_brakes)}")
    parts.append(f"dd={drawdown_pct*100:.1f}%")
    parts.append(f"var99={var_99_pct*100:.2f}%")
    parts.append(f"regime={regime_label}")
    parts.append(f"kelly_mult={kelly_multiplier:.3f}")
    if not blocking_brakes and not reducing_brakes:
        parts.append("all_clear")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# RiskStateSnapshot
# ---------------------------------------------------------------------------


@dataclass
class RiskStateSnapshot:
    """Unified, serializable snapshot of the entire risk system state."""

    snapshot_id: str
    session_id: str
    timestamp: float
    risk_level: RiskLevel
    composite_score: int
    committee_verdict: dict[str, Any]
    blocking_brakes: list[str]
    reducing_brakes: list[str]
    drawdown_pct: float
    drawdown_state: str
    var_99_pct: float
    regime_label: str
    kelly_multiplier: float
    veto_narrative: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "risk_level": self.risk_level.value,
            "composite_score": self.composite_score,
            "committee_verdict": self.committee_verdict,
            "blocking_brakes": self.blocking_brakes,
            "reducing_brakes": self.reducing_brakes,
            "drawdown_pct": round(self.drawdown_pct, 6),
            "drawdown_state": self.drawdown_state,
            "var_99_pct": round(self.var_99_pct, 6),
            "regime_label": self.regime_label,
            "kelly_multiplier": round(self.kelly_multiplier, 4),
            "veto_narrative": self.veto_narrative,
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# SQL schema
# ---------------------------------------------------------------------------

_CREATE_RISK_STATE_SQL = """
CREATE TABLE IF NOT EXISTS risk_state_snapshots (
    snapshot_id   TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL DEFAULT 'unknown',
    timestamp     REAL NOT NULL,
    risk_level    TEXT NOT NULL,
    composite_score INTEGER NOT NULL,
    blocking_brakes TEXT NOT NULL,
    reducing_brakes TEXT NOT NULL,
    drawdown_pct  REAL NOT NULL DEFAULT 0.0,
    drawdown_state TEXT NOT NULL DEFAULT 'normal',
    var_99_pct    REAL NOT NULL DEFAULT 0.0,
    regime_label  TEXT NOT NULL DEFAULT 'unknown',
    kelly_multiplier REAL NOT NULL DEFAULT 1.0,
    veto_narrative TEXT NOT NULL DEFAULT '',
    payload_json  TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_RISK_STATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_rss_timestamp
ON risk_state_snapshots(timestamp DESC)
"""

_CREATE_RISK_STATE_SESSION_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_rss_session
ON risk_state_snapshots(session_id, timestamp DESC)
"""


# ---------------------------------------------------------------------------
# RiskStateStore
# ---------------------------------------------------------------------------


class RiskStateStore:
    """Persists RiskStateSnapshot records to quant_analytics.db.

    Uses WAL mode and INSERT OR IGNORE (idempotent by snapshot_id).
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from wallet_manager.config import get_settings
            db_path = get_settings().quant_analytics_db_path
        self._db_path = Path(db_path)
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_RISK_STATE_SQL)
            conn.execute(_CREATE_RISK_STATE_INDEX_SQL)
            conn.execute(_CREATE_RISK_STATE_SESSION_INDEX_SQL)
            conn.commit()
        self._initialized = True

    def record(self, snapshot: RiskStateSnapshot) -> None:
        """Persist a snapshot. Silently skips on duplicate snapshot_id."""
        try:
            self._ensure_initialized()
            payload = json.dumps(snapshot.to_dict(), ensure_ascii=True, sort_keys=True)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO risk_state_snapshots (
                        snapshot_id, session_id, timestamp, risk_level,
                        composite_score, blocking_brakes, reducing_brakes,
                        drawdown_pct, drawdown_state, var_99_pct, regime_label,
                        kelly_multiplier, veto_narrative, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.snapshot_id,
                        snapshot.session_id,
                        snapshot.timestamp,
                        snapshot.risk_level.value,
                        snapshot.composite_score,
                        json.dumps(snapshot.blocking_brakes),
                        json.dumps(snapshot.reducing_brakes),
                        snapshot.drawdown_pct,
                        snapshot.drawdown_state,
                        snapshot.var_99_pct,
                        snapshot.regime_label,
                        snapshot.kelly_multiplier,
                        snapshot.veto_narrative,
                        payload,
                    ),
                )
                conn.commit()
        except Exception as exc:
            log.warning("RiskStateStore.record failed: %s", exc)

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent N snapshots, newest first."""
        try:
            self._ensure_initialized()
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """
                    SELECT snapshot_id, session_id, timestamp, risk_level,
                           composite_score, blocking_brakes, reducing_brakes,
                           drawdown_pct, drawdown_state, var_99_pct,
                           regime_label, kelly_multiplier, veto_narrative
                    FROM risk_state_snapshots
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "snapshot_id": row["snapshot_id"],
                    "session_id": row["session_id"],
                    "timestamp": row["timestamp"],
                    "risk_level": row["risk_level"],
                    "composite_score": row["composite_score"],
                    "blocking_brakes": json.loads(row["blocking_brakes"]),
                    "reducing_brakes": json.loads(row["reducing_brakes"]),
                    "drawdown_pct": row["drawdown_pct"],
                    "drawdown_state": row["drawdown_state"],
                    "var_99_pct": row["var_99_pct"],
                    "regime_label": row["regime_label"],
                    "kelly_multiplier": row["kelly_multiplier"],
                    "veto_narrative": row["veto_narrative"],
                })
            return result
        except Exception as exc:
            log.warning("RiskStateStore.get_recent failed: %s", exc)
            return []

    def get_risk_trajectory(self, hours: int = 24) -> list[dict[str, Any]]:
        """Return (timestamp, risk_level, composite_score) series for the past N hours."""
        try:
            self._ensure_initialized()
            cutoff = time.time() - hours * 3600.0
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    """
                    SELECT timestamp, risk_level, composite_score, drawdown_pct, var_99_pct
                    FROM risk_state_snapshots
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    """,
                    (cutoff,),
                )
                rows = cur.fetchall()
            return [
                {
                    "timestamp": row["timestamp"],
                    "risk_level": row["risk_level"],
                    "composite_score": row["composite_score"],
                    "drawdown_pct": row["drawdown_pct"],
                    "var_99_pct": row["var_99_pct"],
                }
                for row in rows
            ]
        except Exception as exc:
            log.warning("RiskStateStore.get_risk_trajectory failed: %s", exc)
            return []

    def count(self) -> int:
        """Return total snapshot count (for tests and diagnostics)."""
        try:
            self._ensure_initialized()
            with sqlite3.connect(self._db_path) as conn:
                cur = conn.execute("SELECT COUNT(*) FROM risk_state_snapshots")
                row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as exc:
            log.warning("RiskStateStore.count failed: %s", exc)
            return 0


# ---------------------------------------------------------------------------
# RiskOS — Facade
# ---------------------------------------------------------------------------


class RiskOS:
    """Unified Risk Operating System.

    Combines RiskCommittee, RiskIntelligence, and DeepKellyRiskEngine
    evaluations into a single RiskStateSnapshot and persists it.

    Usage::

        ros = get_risk_os()
        snapshot = await ros.evaluate_and_record(
            paper_engine=engine,
            confidence=0.65,
            regime_label="low_vol",
            session_id=session_id,
        )
        if snapshot.risk_level == RiskLevel.RED:
            log.warning("Risk OS: RED — %s", snapshot.veto_narrative)
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._store = RiskStateStore(db_path)
        self._last_snapshot: RiskStateSnapshot | None = None

    async def evaluate_and_record(
        self,
        paper_engine: Any | None = None,
        confidence: float = 0.0,
        spread_bps: float = 0.0,
        pool_depth_usd: float = 0.0,
        model_disagreement: float = 0.0,
        current_price: float = 0.0,
        regime_label: str = "unknown",
        equity_usd: float = 10_000.0,
        session_id: str = "unknown",
    ) -> RiskStateSnapshot:
        """Evaluate all risk components and return a unified snapshot.

        The snapshot is also persisted to the DB and stored as
        ``_last_snapshot`` for subsequent ``to_dict()`` calls.
        """
        # --- 1. RiskCommittee ---
        committee_verdict_dict: dict[str, Any] = {}
        blocking_brakes: list[str] = []
        reducing_brakes: list[str] = []
        try:
            from wallet_manager.risk_committee import get_paper_risk_committee
            verdict = await get_paper_risk_committee().evaluate(
                paper_engine=paper_engine,
                confidence=confidence,
                spread_bps=spread_bps,
                pool_depth_usd=pool_depth_usd,
                model_disagreement=model_disagreement,
                current_price=current_price,
            )
            committee_verdict_dict = verdict.to_dict()
            blocking_brakes = verdict.blocking_brakes
            from wallet_manager.risk_committee import BrakeVerdict
            reducing_brakes = [
                r.brake_name
                for r in verdict.brake_results
                if r.verdict == BrakeVerdict.REDUCE
            ]
        except Exception as exc:
            log.debug("RiskOS: committee eval failed: %s", exc)

        # --- 2. RiskIntelligence ---
        drawdown_pct = 0.0
        drawdown_state = "normal"
        var_99_pct = 0.0
        kelly_multiplier = 1.0
        try:
            from wallet_manager.risk_intelligence import get_risk_intelligence
            ri = get_risk_intelligence(equity_usd)
            ri.record_cycle(equity_usd=equity_usd, pct_return=0.0, regime_label=regime_label)
            dd_dict = ri.drawdown_accel.to_dict()
            drawdown_pct = float(dd_dict.get("current_drawdown_pct", 0.0)) / 100.0
            var_report = ri.fat_tail_var.get_var_report(equity_usd)
            var_99_pct = float(var_report.get("var_99_pct", 0.0)) / 100.0
            kelly_multiplier = float(ri.get_effective_kelly_multiplier(regime_label))
        except Exception as exc:
            log.debug("RiskOS: intelligence eval failed: %s", exc)

        # --- 3. DeepKelly drawdown state ---
        try:
            from wallet_manager.strategies.deep_kelly_risk import get_deep_kelly_engine
            dk = get_deep_kelly_engine()
            dk_state = dk.drawdown.state
            if dk_state in ("halted", "reduced"):
                drawdown_state = dk_state
            drawdown_pct = max(drawdown_pct, dk.drawdown.drawdown_pct)
        except Exception as exc:
            log.debug("RiskOS: deep kelly eval failed: %s", exc)

        # --- 4. Composite scoring ---
        composite_score = _compute_composite_score(
            blocking_brakes, reducing_brakes, drawdown_pct, var_99_pct
        )
        risk_level = _classify_risk_level(blocking_brakes, reducing_brakes, composite_score)
        veto_narrative = _build_veto_narrative(
            blocking_brakes, reducing_brakes, risk_level, composite_score,
            drawdown_pct, var_99_pct, regime_label, kelly_multiplier,
        )

        snapshot = RiskStateSnapshot(
            snapshot_id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=time.time(),
            risk_level=risk_level,
            composite_score=composite_score,
            committee_verdict=committee_verdict_dict,
            blocking_brakes=blocking_brakes,
            reducing_brakes=reducing_brakes,
            drawdown_pct=drawdown_pct,
            drawdown_state=drawdown_state,
            var_99_pct=var_99_pct,
            regime_label=regime_label,
            kelly_multiplier=kelly_multiplier,
            veto_narrative=veto_narrative,
        )

        self._store.record(snapshot)
        self._last_snapshot = snapshot
        return snapshot

    def get_store(self) -> RiskStateStore:
        return self._store

    def to_dict(self) -> dict[str, Any]:
        """Return the last evaluated snapshot + recent history."""
        recent = self._store.get_recent(20)
        trajectory = self._store.get_risk_trajectory(24)
        return {
            "generated_at": time.time(),
            "last_snapshot": self._last_snapshot.to_dict() if self._last_snapshot else None,
            "recent_snapshots": recent,
            "trajectory_24h": trajectory,
            "total_snapshots": self._store.count(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_risk_os: RiskOS | None = None


def get_risk_os(db_path: str | Path | None = None) -> RiskOS:
    """Return the module-level RiskOS singleton."""
    global _risk_os
    if _risk_os is None:
        _risk_os = RiskOS(db_path)
    return _risk_os
