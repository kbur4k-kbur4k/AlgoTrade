"""
wallet_manager/data/data_quality.py
=====================================
Phase 4 — Data Layer: Data governance and quality SLOs.

Prevents silent data failures by enforcing explicit quality contracts
on every dataset before it is used for research or training.

Usage::

    sla = DataQualitySLA(
        dataset_id="ds_eth_5m_2024Q1_v1",
        min_row_count=50_000,
        max_missing_pct=2.0,
        max_spike_count=50,
        max_stale_count=100,
    )

    monitor = DataQualityMonitor()
    await monitor.initialize()

    report = DataQualityReport(
        dataset_id="ds_eth_5m_2024Q1_v1",
        row_count=52_000,
        missing_pct=0.5,
        spike_count=3,
        stale_count=0,
    )
    result = monitor.validate(report, sla)
    print(result.passed, result.violations)

    await monitor.record(result)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import aiosqlite

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)

_DEFAULT_DB = os.getenv("DATASET_REGISTRY_DB_PATH", "dataset_registry.db")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS data_quality_audits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id      TEXT    NOT NULL,
    checked_at      REAL    NOT NULL,
    passed          INTEGER NOT NULL,
    violations      TEXT    NOT NULL DEFAULT '[]',   -- JSON list of violation strings
    metrics         TEXT    NOT NULL DEFAULT '{}',   -- JSON dict of measured values
    sla_snapshot    TEXT    NOT NULL DEFAULT '{}'    -- JSON dict of SLA at check time
);
CREATE INDEX IF NOT EXISTS idx_dqa_dataset ON data_quality_audits(dataset_id);
CREATE INDEX IF NOT EXISTS idx_dqa_checked ON data_quality_audits(checked_at);
CREATE INDEX IF NOT EXISTS idx_dqa_passed  ON data_quality_audits(passed);
"""


@dataclass
class DataQualitySLA:
    """Quality thresholds for a dataset.

    Attributes:
        dataset_id: Which dataset this SLA applies to.
        min_row_count: Minimum number of rows required.
        max_missing_pct: Maximum allowed percentage of missing/null values.
        max_spike_count: Maximum number of spike-flagged rows.
        max_stale_count: Maximum number of stale-flagged rows.
        max_purge_zone_pct: Maximum percentage of rows in purge zone.
        required_sources: At least one of these sources must be present.
        staleness_threshold_seconds: If data is older than this, fail.
        notes: Free-text rationale for these SLA values.
    """

    dataset_id: str
    min_row_count: int = 50_000
    max_missing_pct: float = 2.0
    max_spike_count: int = 200
    max_stale_count: int = 500
    max_purge_zone_pct: float = 5.0
    required_sources: list[str] = field(default_factory=lambda: ["uniswap_subgraph", "defillama"])
    staleness_threshold_seconds: int = 86_400 * 7  # 7 days
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["required_sources"] = json.dumps(d["required_sources"])
        return d


@dataclass
class DataQualityReport:
    """Measured quality metrics for a dataset at a point in time.

    Attributes:
        dataset_id: Which dataset was measured.
        row_count: Measured row count.
        missing_pct: Measured missing value percentage.
        spike_count: Count of spike-flagged rows.
        stale_count: Count of stale-flagged rows.
        purge_zone_pct: Percentage of rows in purge zone.
        sources_present: Data sources found in dataset.
        latest_row_ts: Unix epoch of most recent row.
        extra: Any additional measured metrics.
    """

    dataset_id: str
    row_count: int = 0
    missing_pct: float = 0.0
    spike_count: int = 0
    stale_count: int = 0
    purge_zone_pct: float = 0.0
    sources_present: list[str] = field(default_factory=list)
    latest_row_ts: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sources_present"] = json.dumps(d["sources_present"])
        d["extra"] = json.dumps(d["extra"])
        return d


@dataclass
class ValidationResult:
    """Result of a DataQualityMonitor.validate() call.

    Attributes:
        dataset_id: Which dataset was validated.
        passed: True if all SLA thresholds were met.
        violations: List of human-readable violation descriptions.
        report: The measured metrics used for validation.
        checked_at: Unix epoch of the check.
    """

    dataset_id: str
    passed: bool
    violations: list[str]
    report: DataQualityReport
    checked_at: float = field(default_factory=time.time)

    def summary(self) -> str:
        status = "PASS" if self.passed else f"FAIL ({len(self.violations)} violations)"
        return f"DataQuality[{self.dataset_id}] {status}"


class DataQualityMonitor:
    """Validates DataQualityReports against SLAs and persists audit records."""

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA_SQL)
            await db.commit()
        self._initialized = True
        log.info("DataQualityMonitor initialized at %s", self._db_path)

    def validate(self, report: DataQualityReport, sla: DataQualitySLA) -> ValidationResult:
        """Check *report* against *sla* and return a ValidationResult.

        Does not persist — call ``record()`` separately.
        """
        violations: list[str] = []

        if report.row_count < sla.min_row_count:
            violations.append(
                f"row_count {report.row_count:,} < min {sla.min_row_count:,}"
            )

        if report.missing_pct > sla.max_missing_pct:
            violations.append(
                f"missing_pct {report.missing_pct:.2f}% > max {sla.max_missing_pct:.2f}%"
            )

        if report.spike_count > sla.max_spike_count:
            violations.append(
                f"spike_count {report.spike_count} > max {sla.max_spike_count}"
            )

        if report.stale_count > sla.max_stale_count:
            violations.append(
                f"stale_count {report.stale_count} > max {sla.max_stale_count}"
            )

        if report.purge_zone_pct > sla.max_purge_zone_pct:
            violations.append(
                f"purge_zone_pct {report.purge_zone_pct:.2f}% > max {sla.max_purge_zone_pct:.2f}%"
            )

        if sla.required_sources:
            present = set(report.sources_present)
            required = set(sla.required_sources)
            missing_sources = required - present
            if missing_sources:
                violations.append(
                    f"required sources missing: {sorted(missing_sources)}"
                )

        if report.latest_row_ts > 0 and sla.staleness_threshold_seconds > 0:
            age_s = time.time() - report.latest_row_ts
            if age_s > sla.staleness_threshold_seconds:
                violations.append(
                    f"data is {age_s / 86400:.1f} days old, "
                    f"threshold is {sla.staleness_threshold_seconds / 86400:.1f} days"
                )

        result = ValidationResult(
            dataset_id=report.dataset_id,
            passed=len(violations) == 0,
            violations=violations,
            report=report,
        )

        if result.passed:
            log.info("DataQuality: %s", result.summary())
        else:
            log.warning("DataQuality: %s — %s", result.summary(), violations)

        return result

    async def record(self, result: ValidationResult) -> None:
        """Persist a ValidationResult to the audit log."""
        await self.initialize()
        metrics = result.report.to_dict()
        sla_snap: dict[str, Any] = {}
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO data_quality_audits
                    (dataset_id, checked_at, passed, violations, metrics, sla_snapshot)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.dataset_id,
                    result.checked_at,
                    int(result.passed),
                    json.dumps(result.violations),
                    json.dumps(metrics),
                    json.dumps(sla_snap),
                ),
            )
            await db.commit()
        log.debug("DataQuality: audit recorded for %s", result.dataset_id)

    async def last_result(self, dataset_id: str) -> dict[str, Any] | None:
        """Return the most recent audit record for *dataset_id*, or None."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM data_quality_audits
                WHERE dataset_id = ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (dataset_id,),
            ) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["violations"] = json.loads(d["violations"])
        d["metrics"] = json.loads(d["metrics"])
        return d

    async def recent_failures(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent failed quality checks across all datasets."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM data_quality_audits
                WHERE passed = 0
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["violations"] = json.loads(d["violations"])
            results.append(d)
        return results
