"""
wallet_manager/promotion_os.py

Phase 9 — Experiment and Promotion Operating System
=====================================================
Unifies experiment tracking and stage-gated promotion into one auditable
OS layer that sits on top of ExperimentLab and the model registry.

Design:
- ExperimentStage  : PAPER → SHADOW → TINY_LIVE → SCALED_LIVE → RETIRED
- PromotionGate    : threshold-checked evidence record for one stage transition
- PromotionRecord  : per-experiment record with current stage + full history
- PromotionStore   : persists records to quant_analytics.db
- PromotionOS      : facade with evaluate(), promote(), demote(), get_scorecard()
- get_promotion_os(): singleton

Exit gate (roadmap §15.7):
  The platform can safely move behavior from paper to capital with evidence.
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


def _default_db() -> Path:
    try:
        from wallet_manager.config import get_settings
        return Path(get_settings().quant_analytics_db_path)
    except Exception:
        return Path("quant_analytics.db")


_DEFAULT_DB = _default_db()


# ---------------------------------------------------------------------------
# Experiment Stage
# ---------------------------------------------------------------------------


class ExperimentStage(StrEnum):
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    TINY_LIVE = "TINY_LIVE"
    SCALED_LIVE = "SCALED_LIVE"
    RETIRED = "RETIRED"


_STAGE_ORDER: list[ExperimentStage] = [
    ExperimentStage.PAPER,
    ExperimentStage.SHADOW,
    ExperimentStage.TINY_LIVE,
    ExperimentStage.SCALED_LIVE,
]


def _next_stage(current: ExperimentStage) -> ExperimentStage | None:
    """Return the next stage or None if already at SCALED_LIVE."""
    try:
        idx = _STAGE_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 < len(_STAGE_ORDER):
        return _STAGE_ORDER[idx + 1]
    return None


# ---------------------------------------------------------------------------
# PromotionGate — evidence threshold for a single stage transition
# ---------------------------------------------------------------------------


@dataclass
class PromotionGate:
    """Evidence threshold result for one metric at one stage transition.

    Attributes:
        gate_id       : UUID.
        experiment_name: Name of the experiment being evaluated.
        from_stage    : Stage being exited.
        to_stage      : Target stage on promotion.
        metric_name   : Name of the evaluated metric.
        threshold     : Minimum value required to pass.
        actual_value  : Observed value.
        passed        : True if actual_value >= threshold.
        evaluated_at  : Unix timestamp.
        notes         : Optional annotation.
    """

    gate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_name: str = ""
    from_stage: str = ExperimentStage.PAPER
    to_stage: str = ExperimentStage.SHADOW
    metric_name: str = ""
    threshold: float = 0.0
    actual_value: float = 0.0
    passed: bool = False
    evaluated_at: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "experiment_name": self.experiment_name,
            "from_stage": self.from_stage,
            "to_stage": self.to_stage,
            "metric_name": self.metric_name,
            "threshold": round(self.threshold, 6),
            "actual_value": round(self.actual_value, 6),
            "passed": self.passed,
            "evaluated_at": self.evaluated_at,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# PromotionRecord — per-experiment current state + history
# ---------------------------------------------------------------------------


@dataclass
class PromotionRecord:
    """Full promotion state for one experiment.

    Attributes:
        record_id      : UUID.
        experiment_name: Unique experiment identifier.
        current_stage  : Current ExperimentStage value.
        promoted_at    : Unix timestamp of last promotion.
        demoted_at     : Unix timestamp of last demotion (or None).
        promotion_count: Total number of promotions.
        demotion_count : Total number of demotions.
        gates_passed   : List of passing PromotionGate dicts.
        gates_failed   : List of failing PromotionGate dicts.
        rollback_rule  : Human-readable rollback trigger description.
        notes          : Optional annotation.
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_name: str = ""
    current_stage: str = ExperimentStage.PAPER
    promoted_at: float | None = None
    demoted_at: float | None = None
    promotion_count: int = 0
    demotion_count: int = 0
    gates_passed: list[dict[str, Any]] = field(default_factory=list)
    gates_failed: list[dict[str, Any]] = field(default_factory=list)
    rollback_rule: str = "Demote on 2+ consecutive losing sessions or drawdown > 5%"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "experiment_name": self.experiment_name,
            "current_stage": self.current_stage,
            "promoted_at": self.promoted_at,
            "demoted_at": self.demoted_at,
            "promotion_count": self.promotion_count,
            "demotion_count": self.demotion_count,
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "rollback_rule": self.rollback_rule,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# PromotionStore — SQLite persistence
# ---------------------------------------------------------------------------


class PromotionStore:
    """Persists PromotionRecord and PromotionGate rows to quant_analytics.db.

    Tables:
      promotion_records : one row per experiment (upserted)
      promotion_gates   : append-only gate evaluations
    """

    RECORDS_DDL = """
    CREATE TABLE IF NOT EXISTS promotion_records (
        record_id        TEXT PRIMARY KEY,
        experiment_name  TEXT NOT NULL UNIQUE,
        current_stage    TEXT NOT NULL,
        promoted_at      REAL,
        demoted_at       REAL,
        promotion_count  INTEGER NOT NULL DEFAULT 0,
        demotion_count   INTEGER NOT NULL DEFAULT 0,
        rollback_rule    TEXT,
        notes            TEXT,
        raw_json         TEXT
    )
    """

    GATES_DDL = """
    CREATE TABLE IF NOT EXISTS promotion_gates (
        gate_id          TEXT PRIMARY KEY,
        experiment_name  TEXT NOT NULL,
        from_stage       TEXT NOT NULL,
        to_stage         TEXT NOT NULL,
        metric_name      TEXT NOT NULL,
        threshold        REAL NOT NULL,
        actual_value     REAL NOT NULL,
        passed           INTEGER NOT NULL,
        evaluated_at     REAL NOT NULL,
        notes            TEXT
    )
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(self.RECORDS_DDL)
                conn.execute(self.GATES_DDL)
                conn.commit()
        except Exception as exc:
            log.warning("PromotionStore: table init failed: %s", exc)

    def save_record(self, record: PromotionRecord) -> bool:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO promotion_records
                    (record_id, experiment_name, current_stage, promoted_at,
                     demoted_at, promotion_count, demotion_count, rollback_rule,
                     notes, raw_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.record_id,
                        record.experiment_name,
                        record.current_stage,
                        record.promoted_at,
                        record.demoted_at,
                        record.promotion_count,
                        record.demotion_count,
                        record.rollback_rule,
                        record.notes,
                        json.dumps(record.to_dict()),
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            log.warning("PromotionStore: save_record failed: %s", exc)
            return False

    def save_gate(self, gate: PromotionGate) -> bool:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO promotion_gates
                    (gate_id, experiment_name, from_stage, to_stage,
                     metric_name, threshold, actual_value, passed,
                     evaluated_at, notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        gate.gate_id,
                        gate.experiment_name,
                        gate.from_stage,
                        gate.to_stage,
                        gate.metric_name,
                        gate.threshold,
                        gate.actual_value,
                        int(gate.passed),
                        gate.evaluated_at,
                        gate.notes,
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            log.warning("PromotionStore: save_gate failed: %s", exc)
            return False

    def load_record(self, experiment_name: str) -> PromotionRecord | None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT raw_json FROM promotion_records WHERE experiment_name=?",
                    (experiment_name,),
                ).fetchone()
            if row is None:
                return None
            d = json.loads(row["raw_json"])
            rec = PromotionRecord(**{
                k: v for k, v in d.items()
                if k in PromotionRecord.__dataclass_fields__
            })
            return rec
        except Exception as exc:
            log.warning("PromotionStore: load_record failed: %s", exc)
            return None

    def list_experiments(self) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT experiment_name, current_stage, promotion_count, "
                    "demotion_count, promoted_at FROM promotion_records "
                    "ORDER BY promoted_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log.warning("PromotionStore: list_experiments failed: %s", exc)
            return []

    def get_gates(self, experiment_name: str, n: int = 20) -> list[dict[str, Any]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM promotion_gates WHERE experiment_name=? "
                    "ORDER BY evaluated_at DESC LIMIT ?",
                    (experiment_name, n),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            log.warning("PromotionStore: get_gates failed: %s", exc)
            return []

    def count_experiments(self) -> int:
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM promotion_records"
                ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# PromotionOS — Phase 9 Facade
# ---------------------------------------------------------------------------


# Default thresholds for each stage gate
_STAGE_GATES: dict[str, list[dict[str, Any]]] = {
    f"{ExperimentStage.PAPER}->{ExperimentStage.SHADOW}": [
        {"metric": "min_cycles", "threshold": 50.0},
        {"metric": "agreement_pct", "threshold": 60.0},
    ],
    f"{ExperimentStage.SHADOW}->{ExperimentStage.TINY_LIVE}": [
        {"metric": "min_cycles", "threshold": 100.0},
        {"metric": "shared_realized_pnl", "threshold": 0.0},
        {"metric": "agreement_pct", "threshold": 65.0},
    ],
    f"{ExperimentStage.TINY_LIVE}->{ExperimentStage.SCALED_LIVE}": [
        {"metric": "min_cycles", "threshold": 200.0},
        {"metric": "shared_realized_pnl", "threshold": 5.0},
        {"metric": "agreement_pct", "threshold": 70.0},
    ],
}


class PromotionOS:
    """Phase 9 Experiment and Promotion Operating System facade.

    Wraps ExperimentLab + PromotionStore to provide:
    - evaluate_promotion(): check gate metrics against thresholds
    - promote(): advance stage if all gates pass
    - demote(): revert stage (rollback)
    - register(): create a new experiment record
    - get_scorecard(): operator-facing unified view
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._store = PromotionStore(db_path)

    def register(
        self,
        experiment_name: str,
        rollback_rule: str = "Demote on 2+ consecutive losing sessions or drawdown > 5%",
        notes: str = "",
    ) -> PromotionRecord:
        """Register a new experiment at PAPER stage."""
        existing = self._store.load_record(experiment_name)
        if existing is not None:
            return existing
        record = PromotionRecord(
            experiment_name=experiment_name,
            current_stage=ExperimentStage.PAPER,
            rollback_rule=rollback_rule,
            notes=notes,
        )
        self._store.save_record(record)
        log.info("PromotionOS: registered experiment '%s'", experiment_name)
        return record

    def evaluate_promotion(
        self,
        experiment_name: str,
        metrics: dict[str, float],
    ) -> list[PromotionGate]:
        """Evaluate whether an experiment passes the gate for the next stage.

        Args:
            experiment_name: Identifier of the experiment.
            metrics: dict of {metric_name: observed_value}.

        Returns:
            List of PromotionGate results (one per gate metric).
            All must pass for promotion to be allowed.
        """
        record = self._store.load_record(experiment_name)
        if record is None:
            record = self.register(experiment_name)

        current = ExperimentStage(record.current_stage)
        target = _next_stage(current)
        if target is None:
            return []

        gate_key = f"{current}->{target}"
        gate_defs = _STAGE_GATES.get(gate_key, [])
        results: list[PromotionGate] = []

        for gdef in gate_defs:
            metric = gdef["metric"]
            threshold = float(gdef["threshold"])
            actual = float(metrics.get(metric, 0.0))
            passed = actual >= threshold
            gate = PromotionGate(
                experiment_name=experiment_name,
                from_stage=current,
                to_stage=target,
                metric_name=metric,
                threshold=threshold,
                actual_value=actual,
                passed=passed,
            )
            self._store.save_gate(gate)
            results.append(gate)

        return results

    def promote(
        self,
        experiment_name: str,
        metrics: dict[str, float],
    ) -> tuple[bool, str, PromotionRecord]:
        """Attempt to promote an experiment to the next stage.

        Returns:
            (promoted: bool, reason: str, updated_record: PromotionRecord)
        """
        gates = self.evaluate_promotion(experiment_name, metrics)
        if not gates:
            record = self._store.load_record(experiment_name) or self.register(experiment_name)
            return False, "No gates defined or already at max stage", record

        all_passed = all(g.passed for g in gates)
        record = self._store.load_record(experiment_name) or self.register(experiment_name)
        current = ExperimentStage(record.current_stage)
        target = _next_stage(current)

        if all_passed and target is not None:
            record.current_stage = target
            record.promoted_at = time.time()
            record.promotion_count += 1
            for g in gates:
                record.gates_passed.append(g.to_dict())
            self._store.save_record(record)
            reason = f"Promoted {current} → {target} ({len(gates)} gates passed)"
            log.info("PromotionOS: %s — %s", experiment_name, reason)
            return True, reason, record

        failed = [g.metric_name for g in gates if not g.passed]
        for g in gates:
            if not g.passed:
                record.gates_failed.append(g.to_dict())
        self._store.save_record(record)
        reason = f"Promotion blocked: failed gates {failed}"
        log.info("PromotionOS: %s — %s", experiment_name, reason)
        return False, reason, record

    def demote(
        self,
        experiment_name: str,
        reason: str = "Manual rollback",
    ) -> PromotionRecord:
        """Demote (rollback) an experiment by one stage."""
        record = self._store.load_record(experiment_name)
        if record is None:
            record = self.register(experiment_name)
            return record

        current = ExperimentStage(record.current_stage)
        try:
            idx = _STAGE_ORDER.index(current)
        except ValueError:
            return record

        if idx > 0:
            record.current_stage = _STAGE_ORDER[idx - 1]
            record.demoted_at = time.time()
            record.demotion_count += 1
            record.notes = f"Demoted: {reason}"
            self._store.save_record(record)
            log.info(
                "PromotionOS: %s demoted %s → %s (%s)",
                experiment_name, current, record.current_stage, reason,
            )
        return record

    def retire(self, experiment_name: str, reason: str = "") -> PromotionRecord:
        """Retire an experiment (terminal state)."""
        record = self._store.load_record(experiment_name)
        if record is None:
            record = self.register(experiment_name)
        record.current_stage = ExperimentStage.RETIRED
        record.notes = f"Retired: {reason}"
        self._store.save_record(record)
        return record

    def get_scorecard(self) -> dict[str, Any]:
        """Operator-facing unified Phase 9 scorecard."""
        experiments = self._store.list_experiments()
        stage_counts: dict[str, int] = {}
        for exp in experiments:
            stage = str(exp.get("current_stage", "PAPER"))
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        lab_report: dict[str, Any] | None = None
        try:
            from wallet_manager.experiment_lab import get_experiment_lab
            lab = get_experiment_lab()
            lab_report = lab.compare_variants()
        except Exception as exc:
            log.debug("PromotionOS scorecard: experiment_lab unavailable: %s", exc)

        return {
            "generated_at": time.time(),
            "phase": 9,
            "total_experiments": self._store.count_experiments(),
            "stage_counts": stage_counts,
            "experiments": experiments,
            "experiment_lab": lab_report,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_promotion_os_instance: PromotionOS | None = None


def get_promotion_os(db_path: Path | str = _DEFAULT_DB) -> PromotionOS:
    """Return the process-wide PromotionOS singleton."""
    global _promotion_os_instance
    if _promotion_os_instance is None:
        _promotion_os_instance = PromotionOS(db_path)
    return _promotion_os_instance
