"""
wallet_manager/execution_os.py

Phase 8 — Execution Operating System
======================================
Unifies all execution components (SmartOrderRouter, SlippageCalibrator,
ExecutionShortfallTracker, ShadowLiveEngine) into a single, auditable,
persistable Execution OS layer.

Design:
- ExecutionRecord    : TCA-style per-trade record (route, slippage, shortfall,
                       cost attribution, shadow deviation)
- ExecutionRecordStore: Persists records to quant_analytics.db for audit
- ExecutionOS        : Facade that records a trade in one call and exposes
                       a unified scorecard
- get_execution_os() : Singleton accessor

Exit gate (roadmap §14.7):
  Execution quality becomes its own measurable optimization surface.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)

# ---------------------------------------------------------------------------
# Database path (same db as Phase 7 RiskOS)
# ---------------------------------------------------------------------------


def _default_db() -> Path:
    try:
        from wallet_manager.config import get_settings
        return Path(get_settings().quant_analytics_db_path)
    except Exception:
        return Path("quant_analytics.db")


_DEFAULT_DB = _default_db()


# ---------------------------------------------------------------------------
# ExecutionRecord — TCA-style per-trade record
# ---------------------------------------------------------------------------


@dataclass
class ExecutionRecord:
    """TCA-style record for a single completed trade.

    Attributes:
        record_id            : UUID for this record.
        timestamp            : Unix timestamp of execution.
        direction            : 'BUY' or 'SELL'.
        size_usd             : Notional trade size in USD.
        route_dex            : DEX used (e.g. 'uniswap_v3', 'sushiswap').
        route_savings_bps    : Basis points saved vs worst available route.
        estimated_slippage_bps: Model's pre-trade slippage estimate (bps).
        actual_slippage_bps  : Realised slippage after fill (bps).
        execution_shortfall  : IS = (fill_price - arrival_price)/arrival_price.
                               Positive = paid more than arrival (adverse).
        cost_attribution_usd : Total execution cost in USD
                               (slippage + gas estimate).
        shadow_deviation_pct : |shadow_price - paper_price| / paper_price * 100.
                               None if shadow mode not active.
        notes                : Free-form annotation.
    """

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    direction: str = "BUY"
    size_usd: float = 0.0
    route_dex: str = ""
    route_savings_bps: float = 0.0
    estimated_slippage_bps: float = 0.0
    actual_slippage_bps: float = 0.0
    execution_shortfall: float = 0.0
    cost_attribution_usd: float = 0.0
    shadow_deviation_pct: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "size_usd": round(self.size_usd, 4),
            "route_dex": self.route_dex,
            "route_savings_bps": round(self.route_savings_bps, 3),
            "estimated_slippage_bps": round(self.estimated_slippage_bps, 3),
            "actual_slippage_bps": round(self.actual_slippage_bps, 3),
            "execution_shortfall": round(self.execution_shortfall, 6),
            "cost_attribution_usd": round(self.cost_attribution_usd, 6),
            "shadow_deviation_pct": (
                round(self.shadow_deviation_pct, 4)
                if self.shadow_deviation_pct is not None
                else None
            ),
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# ExecutionRecordStore — SQLite persistence
# ---------------------------------------------------------------------------


class ExecutionRecordStore:
    """Persists ExecutionRecord rows to quant_analytics.db.

    Table: execution_records
    Columns: record_id, timestamp, direction, size_usd, route_dex,
             route_savings_bps, estimated_slippage_bps, actual_slippage_bps,
             execution_shortfall, cost_attribution_usd,
             shadow_deviation_pct, notes, raw_json
    """

    TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS execution_records (
        record_id              TEXT PRIMARY KEY,
        timestamp              REAL NOT NULL,
        direction              TEXT NOT NULL,
        size_usd               REAL NOT NULL,
        route_dex              TEXT NOT NULL,
        route_savings_bps      REAL NOT NULL,
        estimated_slippage_bps REAL NOT NULL,
        actual_slippage_bps    REAL NOT NULL,
        execution_shortfall    REAL NOT NULL,
        cost_attribution_usd   REAL NOT NULL,
        shadow_deviation_pct   REAL,
        notes                  TEXT,
        raw_json               TEXT
    )
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._db_path = Path(db_path)
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(self.TABLE_DDL)
                conn.commit()
        except Exception as exc:
            log.warning("ExecutionRecordStore: table init failed: %s", exc)

    def save(self, record: ExecutionRecord) -> bool:
        """Persist a single ExecutionRecord. Returns True on success."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO execution_records
                    (record_id, timestamp, direction, size_usd, route_dex,
                     route_savings_bps, estimated_slippage_bps,
                     actual_slippage_bps, execution_shortfall,
                     cost_attribution_usd, shadow_deviation_pct, notes,
                     raw_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.record_id,
                        record.timestamp,
                        record.direction,
                        record.size_usd,
                        record.route_dex,
                        record.route_savings_bps,
                        record.estimated_slippage_bps,
                        record.actual_slippage_bps,
                        record.execution_shortfall,
                        record.cost_attribution_usd,
                        record.shadow_deviation_pct,
                        record.notes,
                        json.dumps(record.to_dict()),
                    ),
                )
                conn.commit()
            return True
        except Exception as exc:
            log.warning("ExecutionRecordStore: save failed: %s", exc)
            return False

    def get_recent(self, n: int = 20) -> list[dict[str, Any]]:
        """Return up to n most recent records as dicts."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM execution_records "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (n,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as exc:
            log.warning("ExecutionRecordStore: get_recent failed: %s", exc)
            return []

    def get_stats(self) -> dict[str, Any]:
        """Aggregate statistics over all persisted records."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*)                             AS total_records,
                        AVG(actual_slippage_bps)            AS avg_actual_slippage_bps,
                        AVG(estimated_slippage_bps)         AS avg_estimated_slippage_bps,
                        AVG(execution_shortfall)            AS avg_shortfall,
                        AVG(route_savings_bps)              AS avg_route_savings_bps,
                        SUM(cost_attribution_usd)           AS total_cost_usd,
                        AVG(shadow_deviation_pct)           AS avg_shadow_deviation_pct
                    FROM execution_records
                    """
                ).fetchone()
                if row is None:
                    return _empty_stats()
                n = int(row["total_records"] or 0)
                if n == 0:
                    return _empty_stats()
                return {
                    "total_records": n,
                    "avg_actual_slippage_bps": round(
                        float(row["avg_actual_slippage_bps"] or 0.0), 3
                    ),
                    "avg_estimated_slippage_bps": round(
                        float(row["avg_estimated_slippage_bps"] or 0.0), 3
                    ),
                    "avg_shortfall": round(
                        float(row["avg_shortfall"] or 0.0), 6
                    ),
                    "avg_route_savings_bps": round(
                        float(row["avg_route_savings_bps"] or 0.0), 3
                    ),
                    "total_cost_usd": round(
                        float(row["total_cost_usd"] or 0.0), 4
                    ),
                    "avg_shadow_deviation_pct": (
                        round(float(row["avg_shadow_deviation_pct"]), 4)
                        if row["avg_shadow_deviation_pct"] is not None
                        else None
                    ),
                }
        except Exception as exc:
            log.warning("ExecutionRecordStore: get_stats failed: %s", exc)
            return _empty_stats()


def _empty_stats() -> dict[str, Any]:
    return {
        "total_records": 0,
        "avg_actual_slippage_bps": 0.0,
        "avg_estimated_slippage_bps": 0.0,
        "avg_shortfall": 0.0,
        "avg_route_savings_bps": 0.0,
        "total_cost_usd": 0.0,
        "avg_shadow_deviation_pct": None,
    }


# ---------------------------------------------------------------------------
# ExecutionOS — Phase 8 Facade
# ---------------------------------------------------------------------------


class ExecutionOS:
    """Phase 8 Execution Operating System facade.

    Ties together:
    - SmartOrderRouter  (route selection, savings measurement)
    - SlippageCalibrator (estimated vs actual slippage)
    - ExecutionShortfallTracker (IS model, rolling 50 trades)
    - ShadowLiveEngine  (paper vs on-chain fill deviation)
    - ExecutionRecordStore (TCA-style persistence)

    Primary entry point: ``record_trade()``.
    Operator-facing view: ``get_scorecard()``.
    """

    def __init__(self, db_path: Path | str = _DEFAULT_DB) -> None:
        self._store = ExecutionRecordStore(db_path)

    # ------------------------------------------------------------------
    # Core record API
    # ------------------------------------------------------------------

    def record_trade(
        self,
        direction: str,
        size_usd: float,
        route_dex: str,
        route_savings_bps: float,
        estimated_slippage_bps: float,
        actual_slippage_bps: float,
        arrival_price: float = 0.0,
        fill_price: float = 0.0,
        shadow_deviation_pct: float | None = None,
        gas_cost_usd: float = 0.0,
        notes: str = "",
    ) -> ExecutionRecord:
        """Record a completed trade execution and persist it.

        Args:
            direction            : 'BUY' or 'SELL'.
            size_usd             : Notional size in USD.
            route_dex            : DEX used for execution.
            route_savings_bps    : Savings vs worst route (bps).
            estimated_slippage_bps: Pre-trade model estimate (bps).
            actual_slippage_bps  : Realised slippage (bps).
            arrival_price        : Mid-price at order submission.
            fill_price           : Actual fill price.
            shadow_deviation_pct : |shadow - paper| / paper * 100, or None.
            gas_cost_usd         : Estimated gas cost for this trade.
            notes                : Optional annotation.

        Returns:
            The persisted ExecutionRecord.
        """
        shortfall = 0.0
        if arrival_price > 0 and fill_price > 0:
            raw = (fill_price - arrival_price) / arrival_price
            shortfall = raw if direction == "BUY" else -raw

        slippage_cost_usd = size_usd * actual_slippage_bps / 10_000.0
        cost_attribution_usd = slippage_cost_usd + gas_cost_usd

        record = ExecutionRecord(
            direction=direction,
            size_usd=size_usd,
            route_dex=route_dex,
            route_savings_bps=route_savings_bps,
            estimated_slippage_bps=estimated_slippage_bps,
            actual_slippage_bps=actual_slippage_bps,
            execution_shortfall=shortfall,
            cost_attribution_usd=cost_attribution_usd,
            shadow_deviation_pct=shadow_deviation_pct,
            notes=notes,
        )

        self._store.save(record)

        try:
            from wallet_manager.strategies.execution_quality import get_execution_quality
            get_execution_quality().calibrator.record(
                estimated_slippage_bps, actual_slippage_bps
            )
        except Exception as exc:
            log.debug("ExecutionOS: calibrator update skipped: %s", exc)

        try:
            from wallet_manager.strategies.smart_order_router import get_smart_order_router
            if arrival_price > 0 and fill_price > 0:
                get_smart_order_router().shortfall_tracker.record(
                    arrival_price, fill_price, direction.lower()
                )
        except Exception as exc:
            log.debug("ExecutionOS: shortfall tracker update skipped: %s", exc)

        log.info(
            "ExecutionOS: %s $%.2f via %s | slippage est=%.1fbps act=%.1fbps "
            "IS=%.4f cost=$%.4f",
            direction,
            size_usd,
            route_dex,
            estimated_slippage_bps,
            actual_slippage_bps,
            shortfall,
            cost_attribution_usd,
        )

        return record

    # ------------------------------------------------------------------
    # Scorecard — operator-facing unified view
    # ------------------------------------------------------------------

    def get_scorecard(self) -> dict[str, Any]:
        """Return unified Phase 8 execution quality scorecard.

        Includes:
        - Persistent aggregate stats from ExecutionRecordStore
        - Live SlippageCalibrator state
        - Live ExecutionShortfallTracker state (rolling 50)
        - ShadowLiveEngine readiness gate
        - Recent trade records (last 10)
        """
        generated_at = time.time()
        scorecard: dict[str, Any] = {
            "generated_at": generated_at,
            "phase": 8,
            "store_stats": self._store.get_stats(),
            "recent_records": self._store.get_recent(10),
        }

        try:
            from wallet_manager.strategies.execution_quality import get_execution_quality
            eq = get_execution_quality()
            scorecard["slippage_calibration"] = eq.calibrator.to_dict()
            scorecard["timing"] = eq.get_timing_snapshot()
        except Exception as exc:
            log.debug("ExecutionOS scorecard: execution_quality unavailable: %s", exc)
            scorecard["slippage_calibration"] = None
            scorecard["timing"] = None

        try:
            from wallet_manager.strategies.smart_order_router import get_smart_order_router
            tracker = get_smart_order_router().shortfall_tracker
            scorecard["shortfall_tracker"] = {
                "trade_count": tracker.trade_count,
                "mean_is": round(tracker.mean_is, 6),
                "median_is": round(tracker.median_is, 6),
                "warn_threshold": tracker.WARN_IS_THRESHOLD,
                "status": (
                    "WARN"
                    if tracker.trade_count >= 5
                    and tracker.mean_is > tracker.WARN_IS_THRESHOLD
                    else "OK"
                ),
            }
        except Exception as exc:
            log.debug("ExecutionOS scorecard: shortfall tracker unavailable: %s", exc)
            scorecard["shortfall_tracker"] = None

        try:
            from wallet_manager.strategies.shadow_live import get_shadow_live_engine
            scorecard["shadow_live"] = get_shadow_live_engine().to_dict()
        except Exception as exc:
            log.debug("ExecutionOS scorecard: shadow_live unavailable: %s", exc)
            scorecard["shadow_live"] = None

        return scorecard


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_execution_os_instance: ExecutionOS | None = None


def get_execution_os(db_path: Path | str = _DEFAULT_DB) -> ExecutionOS:
    """Return the process-wide ExecutionOS singleton."""
    global _execution_os_instance
    if _execution_os_instance is None:
        _execution_os_instance = ExecutionOS(db_path)
    return _execution_os_instance
