"""
wallet_manager/learning_os.py

Phase 10 — Continuous Learning Operating System
=================================================
Unifies ContinuousLearner (drift review, setup decay, threshold retuning,
feature importance drift) into a single auditable OS layer.

Design:
- LearningCycle      : one complete evidence review snapshot
- LearningCycleStore : persists cycles to quant_analytics.db
- LearningOS         : facade with run_cycle() and get_scorecard()
- get_learning_os()  : singleton

Exit gate (roadmap §16.7):
  The platform evolves with evidence instead of intuition.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)


def _default_db() -> Path:
    try:
        from wallet_manager.config import get_settings
        return Path(get_settings().quant_analytics_db_path)
    except Exception:
        return Path("quant_analytics.db")


_DEFAULT_DB = _default_db()
_RETRAIN_INTERVAL_DAYS: float = 7.0   # recommend retraining after this many days


# ---------------------------------------------------------------------------
# LearningCycle — one complete evidence review
# ---------------------------------------------------------------------------


@dataclass
class LearningCycle:
    """Snapshot from one run of the evidence review loop.

    Attributes:
        cycle_id            : UUID.
        timestamp           : Unix timestamp.
        drift_level         : NOMINAL / MILD / MODERATE / SEVERE.
        drift_trend         : stable / increasing / decreasing.
        drift_alert         : True if drift warrants action.
        setup_decay_count   : Number of setups showing decay.
        stable_setup_count  : Number of stable setups.
        feature_alert_count : Number of feature importance decay alerts.
        suggestions_count   : Number of threshold suggestions generated.
        alerts              : Human-readable alert strings.
        notes               : Optional annotation.
    """

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    drift_level: str = "UNKNOWN"
    drift_trend: str = "stable"
    drift_alert: bool = False
    setup_decay_count: int = 0
    stable_setup_count: int = 0
    feature_alert_count: int = 0
    suggestions_count: int = 0
    alerts: list[str] = field(default_factory=list)
    notes: str = ""
    retraining_recommended: bool = False
    model_age_days: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "timestamp": self.timestamp,
            "drift_level": self.drift_level,
            "drift_trend": self.drift_trend,
            "drift_alert": self.drift_alert,
            "setup_decay_count": self.setup_decay_count,
            "stable_setup_count": self.stable_setup_count,
            "feature_alert_count": self.feature_alert_count,
            "suggestions_count": self.suggestions_count,
            "alerts": self.alerts,
            "notes": self.notes,
            "retraining_recommended": self.retraining_recommended,
            "model_age_days": round(self.model_age_days, 1),
        }


# ---------------------------------------------------------------------------
# LearningCycleStore — SQLite persistence
# ---------------------------------------------------------------------------


class LearningCycleStore:
    """Persists LearningCycle rows to quant_analytics.db.

    Table: learning_cycles
    """

    TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS learning_cycles (
        cycle_id                TEXT PRIMARY KEY,
        timestamp               REAL NOT NULL,
        drift_level             TEXT NOT NULL,
        drift_trend             TEXT NOT NULL,
        drift_alert             INTEGER NOT NULL,
        setup_decay_count       INTEGER NOT NULL,
        stable_setup_count      INTEGER NOT NULL,
        feature_alert_count     INTEGER NOT NULL,
        suggestions_count       INTEGER NOT NULL,
        notes                   TEXT,
        raw_json                TEXT,
        retraining_recommended  INTEGER NOT NULL DEFAULT 0,
        model_age_days          REAL NOT NULL DEFAULT 0.0
    )
    """

    _MIGRATIONS = [
        "ALTER TABLE learning_cycles ADD COLUMN retraining_recommended INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE learning_cycles ADD COLUMN model_age_days REAL NOT NULL DEFAULT 0.0",
    ]

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(self.TABLE_DDL)
                conn.commit()
                for migration in self._MIGRATIONS:
                    try:
                        conn.execute(migration)
                        conn.commit()
                    except sqlite3.OperationalError:
                        pass  # column already exists
        except Exception as exc:
            log.warning("LearningCycleStore: table init failed: %s", exc)

    def save(self, cycle: LearningCycle) -> bool:
        """Persist a LearningCycle. Returns True on success."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO learning_cycles
                    (cycle_id, timestamp, drift_level, drift_trend, drift_alert,
                     setup_decay_count, stable_setup_count, feature_alert_count,
                     suggestions_count, notes, raw_json,
                     retraining_recommended, model_age_days)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        cycle.cycle_id,
                        cycle.timestamp,
                        cycle.drift_level,
                        cycle.drift_trend,
                        int(cycle.drift_alert),
                        cycle.setup_decay_count,
                        cycle.stable_setup_count,
                        cycle.feature_alert_count,
                        cycle.suggestions_count,
                        cycle.notes,
                        json.dumps(cycle.to_dict()),
                        int(cycle.retraining_recommended),
                        cycle.model_age_days,
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            log.warning("LearningCycleStore: save failed: %s", exc)
            return False

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Return up to n most recent cycles as dicts."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM learning_cycles ORDER BY timestamp DESC LIMIT ?",
                    (n,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            log.warning("LearningCycleStore: get_recent failed: %s", exc)
            return []

    def get_stats(self) -> dict[str, Any]:
        """Aggregate statistics over all persisted cycles."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*)                        AS total_cycles,
                        SUM(drift_alert)                AS total_drift_alerts,
                        AVG(setup_decay_count)          AS avg_decay_count,
                        AVG(feature_alert_count)        AS avg_feature_alerts,
                        AVG(suggestions_count)          AS avg_suggestions
                    FROM learning_cycles
                    """
                ).fetchone()
            if row is None or int(row["total_cycles"] or 0) == 0:
                return _empty_stats()
            return {
                "total_cycles": int(row["total_cycles"]),
                "total_drift_alerts": int(row["total_drift_alerts"] or 0),
                "avg_decay_count": round(float(row["avg_decay_count"] or 0.0), 2),
                "avg_feature_alerts": round(float(row["avg_feature_alerts"] or 0.0), 2),
                "avg_suggestions": round(float(row["avg_suggestions"] or 0.0), 2),
            }
        except Exception as exc:
            log.warning("LearningCycleStore: get_stats failed: %s", exc)
            return _empty_stats()

    def count(self) -> int:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM learning_cycles").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0


def _empty_stats() -> dict[str, Any]:
    return {
        "total_cycles": 0,
        "total_drift_alerts": 0,
        "avg_decay_count": 0.0,
        "avg_feature_alerts": 0.0,
        "avg_suggestions": 0.0,
    }


# ---------------------------------------------------------------------------
# LearningOS — Phase 10 Facade
# ---------------------------------------------------------------------------


class LearningOS:
    """Phase 10 Continuous Learning Operating System facade.

    Wraps ContinuousLearner and persists each evidence review run as a
    LearningCycle so operators have a historical record of drift events,
    setup decay, feature alerts, and threshold suggestions.

    Primary entry point: ``run_cycle(paper_engine)``
    Operator-facing view: ``get_scorecard()``
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._store = LearningCycleStore(db_path)

    @staticmethod
    def _check_model_age() -> tuple[float, bool]:
        """Read training_report.json and return (age_days, retraining_recommended).

        Returns (0.0, False) if the report cannot be read.
        """
        report_path = Path(__file__).resolve().parent / "ml_models" / "training_report.json"
        try:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            trained_at_str = data.get("trained_at") or data.get("generated_at", "")
            if not trained_at_str:
                return 0.0, False
            trained_at = datetime.fromisoformat(trained_at_str)
            if trained_at.tzinfo is None:
                trained_at = trained_at.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - trained_at).total_seconds() / 86400.0
            return round(age_days, 1), age_days >= _RETRAIN_INTERVAL_DAYS
        except Exception as exc:
            log.debug("LearningOS: could not read training_report.json: %s", exc)
            return 0.0, False

    async def run_cycle(self, paper_engine: Any | None = None) -> LearningCycle:
        """Run a full learning review and persist the result.

        Args:
            paper_engine: Optional paper engine for setup decay / threshold analysis.

        Returns:
            The persisted LearningCycle.
        """
        from wallet_manager.continuous_learning import get_continuous_learner

        learner = get_continuous_learner()
        report = await learner.generate_learning_report(paper_engine=paper_engine)

        drift = report.get("drift") or {}
        setup_decay = report.get("setup_decay") or {}
        suggestions = report.get("threshold_suggestions") or []
        feat_drift = report.get("feature_drift") or {}
        alerts: list[str] = list(report.get("alerts") or [])

        model_age_days, retraining_recommended = self._check_model_age()
        if retraining_recommended:
            alerts.append(
                f"RETRAIN_RECOMMENDED: models are {model_age_days:.1f} days old "
                f"(threshold={_RETRAIN_INTERVAL_DAYS:.0f}d). "
                "Run: python scripts/train_models.py"
            )
            log.warning(
                "LearningOS: models are %.1f days old — retraining recommended. "
                "Run: python scripts/train_models.py",
                model_age_days,
            )

        cycle = LearningCycle(
            drift_level=str(drift.get("recent_level", "UNKNOWN")),
            drift_trend=str(drift.get("trend", "stable")),
            drift_alert=bool(drift.get("alert", False)),
            setup_decay_count=len(setup_decay.get("decaying", [])),
            stable_setup_count=len(setup_decay.get("stable", [])),
            feature_alert_count=int(feat_drift.get("total_alerts", 0)),
            suggestions_count=len(suggestions),
            alerts=alerts[:20],
            retraining_recommended=retraining_recommended,
            model_age_days=model_age_days,
        )

        self._store.save(cycle)

        log.info(
            "LearningOS: cycle=%s drift=%s trend=%s decay=%d feat_alerts=%d "
            "suggestions=%d model_age=%.1fd retrain=%s",
            cycle.cycle_id[:8],
            cycle.drift_level,
            cycle.drift_trend,
            cycle.setup_decay_count,
            cycle.feature_alert_count,
            cycle.suggestions_count,
            cycle.model_age_days,
            cycle.retraining_recommended,
        )

        return cycle

    def get_scorecard(self) -> dict[str, Any]:
        """Return unified Phase 10 learning scorecard.

        Includes:
        - Aggregate stats from LearningCycleStore
        - Live ContinuousLearner state (drift reviewer, feature drift)
        - Recent cycles
        """
        generated_at = time.time()
        scorecard: dict[str, Any] = {
            "generated_at": generated_at,
            "phase": 10,
            "store_stats": self._store.get_stats(),
            "recent_cycles": self._store.get_recent(5),
        }

        try:
            from wallet_manager.continuous_learning import get_continuous_learner
            learner = get_continuous_learner()
            scorecard["drift_summary"] = learner.drift_reviewer.trend_summary()
            scorecard["feature_drift"] = learner.feature_drift.to_dict()
            scorecard["recent_changelog"] = learner.changelog.recent(3)
        except Exception as exc:
            log.debug("LearningOS scorecard: continuous_learning unavailable: %s", exc)
            scorecard["drift_summary"] = None
            scorecard["feature_drift"] = None
            scorecard["recent_changelog"] = None

        return scorecard


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_learning_os_instance: LearningOS | None = None


def get_learning_os(db_path: Path | str = _DEFAULT_DB) -> LearningOS:
    """Return the process-wide LearningOS singleton."""
    global _learning_os_instance
    if _learning_os_instance is None:
        _learning_os_instance = LearningOS(db_path)
    return _learning_os_instance
