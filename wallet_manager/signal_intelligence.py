"""
wallet_manager/signal_intelligence.py

Sprint JS-1: Signal Intelligence Layer
=======================================
Implements four institutional-grade signal quality monitors:

JS-1.1  ICTracker          — Information Coefficient per signal (rolling Pearson)
JS-1.2  SignalDecayAnalyzer — PnL decay curve after signal generation
JS-1.3  SignalCorrelationMatrix — Detect redundant signals (|corr| > 0.70)
JS-1.4  EnsembleDiversityScore — Measure model disagreement rate

All components are stateful singletons, feed from the shadow cycle, and
expose to_dict() for dashboard + API consumption.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import sqlite3
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)

# ---------------------------------------------------------------------------
# JS-1.1  Information Coefficient (IC) Tracker
# ---------------------------------------------------------------------------

_IC_WINDOW = 100          # observations for rolling IC
_IC_FORWARD_MINUTES = 30  # measure forward return N minutes after signal


@dataclass
class ICObservation:
    timestamp: float
    signal_name: str
    signal_value: float
    price_at_signal: float
    forward_price: float = 0.0
    forward_return: float = 0.0
    resolved: bool = False


class ICTracker:
    """
    Tracks Information Coefficient (IC) = Pearson corr(signal, forward_return)
    for each named signal over a rolling window.

    Usage in shadow cycle:
        tracker.record_signal("robust_alpha", alpha_value, current_price)

    After forward_minutes have elapsed:
        tracker.resolve_pending(current_price, current_time)

    Weekly report:
        tracker.get_ic_report()
    """

    def __init__(self, forward_minutes: float = _IC_FORWARD_MINUTES, window: int = _IC_WINDOW) -> None:
        self._forward_seconds = forward_minutes * 60.0
        self._window = window
        self._pending: list[ICObservation] = []
        self._resolved: dict[str, deque[ICObservation]] = {}

    def record_signal(self, signal_name: str, signal_value: float, price: float) -> None:
        """Record a signal value and current price for future IC calculation."""
        self._pending.append(ICObservation(
            timestamp=time.time(),
            signal_name=signal_name,
            signal_value=signal_value,
            price_at_signal=price,
        ))

    def resolve_pending(self, current_price: float, now: float | None = None) -> int:
        """Resolve pending observations whose forward window has elapsed."""
        now = now or time.time()
        resolved_count = 0
        still_pending: list[ICObservation] = []
        for obs in self._pending:
            if now - obs.timestamp >= self._forward_seconds:
                if obs.price_at_signal > 0:
                    obs.forward_price = current_price
                    obs.forward_return = (current_price - obs.price_at_signal) / obs.price_at_signal
                obs.resolved = True
                if obs.signal_name not in self._resolved:
                    self._resolved[obs.signal_name] = deque(maxlen=self._window)
                self._resolved[obs.signal_name].append(obs)
                resolved_count += 1
            else:
                still_pending.append(obs)
        self._pending = still_pending
        return resolved_count

    def compute_ic(self, signal_name: str) -> float:
        """Return rolling IC for a signal. Returns 0.0 if insufficient data."""
        obs_list = list(self._resolved.get(signal_name, []))
        if len(obs_list) < 10:
            return 0.0
        signals = [o.signal_value for o in obs_list]
        returns = [o.forward_return for o in obs_list]
        return _pearson(signals, returns)

    def get_ic_status(self, signal_name: str) -> str:
        ic = self.compute_ic(signal_name)
        if ic >= 0.05:
            return "WORKING"
        if ic >= 0.02:
            return "WEAK"
        return "NOISE"

    def get_ic_report(self) -> dict[str, Any]:
        signals = list(self._resolved.keys())
        rows: list[dict[str, Any]] = []
        for name in signals:
            ic = self.compute_ic(name)
            n = len(self._resolved[name])
            rows.append({
                "signal": name,
                "ic": round(ic, 5),
                "n_observations": n,
                "status": self.get_ic_status(name),
            })
        rows.sort(key=lambda r: r["ic"], reverse=True)
        return {
            "generated_at": time.time(),
            "forward_minutes": self._forward_seconds / 60.0,
            "window": self._window,
            "signals": rows,
            "pending_count": len(self._pending),
            "alerts": [r["signal"] for r in rows if r["status"] == "NOISE" and r["n_observations"] >= 20],
        }


# ---------------------------------------------------------------------------
# JS-1.2  Signal Decay Analyzer
# ---------------------------------------------------------------------------

_DECAY_HORIZONS_S = [5 * 60, 15 * 60, 30 * 60, 60 * 60, 4 * 60 * 60]  # 5m,15m,30m,1h,4h


@dataclass
class DecayObservation:
    timestamp: float
    price_at_signal: float
    signal_direction: int        # +1 for long signal, -1 for short
    pnl_by_horizon: dict[int, float] = field(default_factory=dict)
    resolved_horizons: set[int] = field(default_factory=set)


class SignalDecayAnalyzer:
    """
    Measures cumulative PnL at multiple horizons after a signal is generated.
    Identifies the optimal hold time for the current strategy.
    """

    def __init__(self, horizons_s: list[int] | None = None) -> None:
        self._horizons = horizons_s or _DECAY_HORIZONS_S
        self._pending: list[DecayObservation] = []
        self._completed: deque[DecayObservation] = deque(maxlen=200)

    def record_signal(self, price: float, direction: int) -> None:
        """Record a new signal for decay analysis. direction: +1=long, -1=short."""
        self._pending.append(DecayObservation(
            timestamp=time.time(),
            price_at_signal=price,
            signal_direction=direction,
        ))

    def update(self, current_price: float, now: float | None = None) -> None:
        """Called each cycle to resolve pending horizon observations."""
        now = now or time.time()
        still_pending: list[DecayObservation] = []
        for obs in self._pending:
            elapsed = now - obs.timestamp
            for h in self._horizons:
                if h not in obs.resolved_horizons and elapsed >= h:
                    ret = (current_price - obs.price_at_signal) / obs.price_at_signal
                    obs.pnl_by_horizon[h] = ret * obs.signal_direction
                    obs.resolved_horizons.add(h)
            if obs.resolved_horizons == set(self._horizons):
                self._completed.append(obs)
            else:
                still_pending.append(obs)
        self._pending = still_pending

    def get_decay_curve(self) -> dict[str, Any]:
        """Return average PnL at each horizon across all completed observations."""
        if not self._completed:
            return {"status": "NO_DATA", "decay_curve": {}, "optimal_hold_minutes": None}
        horizon_pnl: dict[int, list[float]] = {h: [] for h in self._horizons}
        for obs in self._completed:
            for h, pnl in obs.pnl_by_horizon.items():
                horizon_pnl[h].append(pnl)
        curve: dict[str, float] = {}
        for h in self._horizons:
            vals = horizon_pnl[h]
            curve[f"{h // 60}m"] = round(sum(vals) / len(vals) * 100, 4) if vals else 0.0
        best_h = max(self._horizons, key=lambda h: sum(horizon_pnl[h]) / max(len(horizon_pnl[h]), 1))
        return {
            "status": "OK",
            "n_completed": len(self._completed),
            "decay_curve_pct": curve,
            "optimal_hold_minutes": best_h // 60,
            "recommendation": f"Most PnL accumulates by {best_h // 60} minutes after signal.",
        }


# ---------------------------------------------------------------------------
# JS-1.3  Signal Correlation Matrix
# ---------------------------------------------------------------------------

_CORR_WINDOW = 200


class SignalCorrelationMatrix:
    """
    Tracks rolling Pearson correlation between all signal dimensions.
    Flags pairs with |corr| > 0.70 as redundant (adding no Sharpe benefit).
    """

    SIGNAL_NAMES = ["robust_alpha", "confidence", "adf_pvalue", "garch_sigma", "spread_bps"]

    def __init__(self, window: int = _CORR_WINDOW) -> None:
        self._window = window
        self._history: dict[str, deque[float]] = {
            name: deque(maxlen=window) for name in self.SIGNAL_NAMES
        }

    def record(
        self,
        robust_alpha: float = 0.0,
        confidence: float = 0.0,
        adf_pvalue: float = 1.0,
        garch_sigma: float = 0.0,
        spread_bps: float = 0.0,
    ) -> None:
        self._history["robust_alpha"].append(robust_alpha)
        self._history["confidence"].append(confidence)
        self._history["adf_pvalue"].append(adf_pvalue)
        self._history["garch_sigma"].append(garch_sigma)
        self._history["spread_bps"].append(spread_bps)

    def get_matrix(self) -> dict[str, Any]:
        n = min(len(v) for v in self._history.values())
        if n < 20:
            return {"status": "INSUFFICIENT_DATA", "n_observations": n, "redundant_pairs": [], "matrix": {}}
        names = self.SIGNAL_NAMES
        matrix: dict[str, dict[str, float]] = {}
        redundant: list[dict[str, Any]] = []
        for i, a in enumerate(names):
            matrix[a] = {}
            for j, b in enumerate(names):
                if i == j:
                    matrix[a][b] = 1.0
                    continue
                xa = list(self._history[a])[-n:]
                xb = list(self._history[b])[-n:]
                corr = _pearson(xa, xb)
                matrix[a][b] = round(corr, 4)
                if i < j and abs(corr) > 0.70:
                    redundant.append({"signal_a": a, "signal_b": b, "correlation": round(corr, 4)})
        return {
            "status": "OK",
            "n_observations": n,
            "matrix": matrix,
            "redundant_pairs": redundant,
            "alert": len(redundant) > 0,
        }


# ---------------------------------------------------------------------------
# JS-1.4  Ensemble Diversity Score
# ---------------------------------------------------------------------------

_DIVERSITY_WINDOW = 100


class EnsembleDiversityScore:
    """
    Measures whether the 4 ML models are genuinely different from each other.
    Diversity = 1 - mean(pairwise agreement rate).
    Target: > 0.25. Below 0.15: ensemble is effectively a single model.
    """

    MODEL_NAMES = ["xgboost", "lightgbm", "lstm", "sklearn"]

    def __init__(self, window: int = _DIVERSITY_WINDOW) -> None:
        self._window = window
        self._predictions: dict[str, deque[int]] = {
            m: deque(maxlen=window) for m in self.MODEL_NAMES
        }

    def record(self, xgboost_signal: int, lightgbm_signal: int, lstm_signal: int, sklearn_signal: int) -> None:
        """Record per-model signal direction: +1=long, -1=short, 0=neutral."""
        self._predictions["xgboost"].append(xgboost_signal)
        self._predictions["lightgbm"].append(lightgbm_signal)
        self._predictions["lstm"].append(lstm_signal)
        self._predictions["sklearn"].append(sklearn_signal)

    def compute_diversity(self) -> float:
        n = min(len(v) for v in self._predictions.values())
        if n < 10:
            return 0.0
        models = self.MODEL_NAMES
        agreement_rates: list[float] = []
        for i in range(len(models)):
            for j in range(i + 1, len(models)):
                a = list(self._predictions[models[i]])[-n:]
                b = list(self._predictions[models[j]])[-n:]
                agree = sum(1 for x, y in zip(a, b, strict=False) if x == y) / n
                agreement_rates.append(agree)
        if not agreement_rates:
            return 0.0
        return round(1.0 - sum(agreement_rates) / len(agreement_rates), 4)

    def get_report(self) -> dict[str, Any]:
        n = min(len(v) for v in self._predictions.values())
        diversity = self.compute_diversity()
        if diversity >= 0.25:
            status = "HEALTHY"
        elif diversity >= 0.15:
            status = "LOW"
        else:
            status = "CRITICAL" if n >= 10 else "INSUFFICIENT_DATA"
        return {
            "diversity_score": diversity,
            "status": status,
            "n_observations": n,
            "target": 0.25,
            "alert": diversity < 0.15 and n >= 10,
            "interpretation": (
                "Models are sufficiently diverse." if status == "HEALTHY"
                else "Models are too similar — ensemble provides minimal Sharpe benefit."
                if status in ("LOW", "CRITICAL") else "Need more observations."
            ),
        }


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient. Returns 0.0 on degenerate input."""
    n = len(x)
    if n < 3 or len(y) != n:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    denom_x = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    denom_y = math.sqrt(sum((yi - my) ** 2 for yi in y))
    denom = denom_x * denom_y
    return num / denom if denom > 1e-12 else 0.0


# ---------------------------------------------------------------------------
# Phase 6 - Signal retirement persistence
# ---------------------------------------------------------------------------


_CREATE_SIGNAL_RETIREMENT_SQL = """
CREATE TABLE IF NOT EXISTS signal_retirement_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint     TEXT NOT NULL UNIQUE,
    recorded_at     REAL NOT NULL,
    signal_name     TEXT NOT NULL,
    ic              REAL NOT NULL,
    ir              REAL NOT NULL,
    composite_score REAL NOT NULL,
    ic_status       TEXT NOT NULL,
    ir_status       TEXT NOT NULL,
    evidence_json   TEXT NOT NULL
)
"""

_CREATE_SIGNAL_RETIREMENT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_signal_retirement_signal_ts
ON signal_retirement_decisions(signal_name, recorded_at DESC)
"""


class SignalRetirementStore:
    """Persist RETIRE recommendations with explicit IC/IR evidence."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from wallet_manager.config import get_settings

            db_path = get_settings().quant_analytics_db_path
        self._db_path = Path(db_path)

    def persist_rows(self, rows: list[Mapping[str, Any]]) -> int:
        """Insert unique retirement decisions and return the insert count."""
        if not rows:
            return 0
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        persisted = 0
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_SIGNAL_RETIREMENT_SQL)
            conn.execute(_CREATE_SIGNAL_RETIREMENT_INDEX_SQL)
            for row in rows:
                evidence = self._build_evidence(row)
                payload = json.dumps(evidence, ensure_ascii=True, sort_keys=True)
                fingerprint_payload = json.dumps(
                    {k: v for k, v in evidence.items() if k != "recorded_at"},
                    ensure_ascii=True,
                    sort_keys=True,
                )
                fingerprint = hashlib.sha1(fingerprint_payload.encode("utf-8")).hexdigest()
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO signal_retirement_decisions (
                        fingerprint, recorded_at, signal_name, ic, ir,
                        composite_score, ic_status, ir_status, evidence_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fingerprint,
                        float(evidence["recorded_at"]),
                        str(evidence["signal"]),
                        float(evidence["ic"]),
                        float(evidence["ir"]),
                        float(evidence["composite_score"]),
                        str(evidence["ic_status"]),
                        str(evidence["ir_status"]),
                        payload,
                    ),
                )
                if cur.rowcount > 0:
                    persisted += 1
            conn.commit()
        return persisted

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent persisted retirement decisions, newest first."""
        if not self._db_path.exists():
            return []
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(_CREATE_SIGNAL_RETIREMENT_SQL)
            conn.execute(_CREATE_SIGNAL_RETIREMENT_INDEX_SQL)
            rows = conn.execute(
                """
                SELECT recorded_at, signal_name, ic, ir, composite_score,
                       ic_status, ir_status, evidence_json
                FROM signal_retirement_decisions
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        recent_rows: list[dict[str, Any]] = []
        for row in rows:
            evidence = {}
            with contextlib.suppress(Exception):
                evidence = json.loads(str(row["evidence_json"]))
            recent_rows.append({
                "recorded_at": row["recorded_at"],
                "signal": row["signal_name"],
                "ic": row["ic"],
                "ir": row["ir"],
                "composite_score": row["composite_score"],
                "ic_status": row["ic_status"],
                "ir_status": row["ir_status"],
                "evidence": evidence if isinstance(evidence, dict) else {},
            })
        return recent_rows

    @staticmethod
    def _build_evidence(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "recorded_at": row.get("recorded_at", time.time()),
            "signal": row.get("signal", "unknown"),
            "ic": round(float(row.get("ic", 0.0)), 6),
            "ir": round(float(row.get("ir", 0.0)), 6),
            "composite_score": round(float(row.get("composite_score", 0.0)), 6),
            "ic_status": row.get("ic_status", "UNKNOWN"),
            "ir_status": row.get("ir_status", "UNKNOWN"),
            "n_observations": int(row.get("n_observations", 0)),
            "n_snapshots": int(row.get("n_snapshots", 0)),
            "retirement_reason": row.get("retirement_reason", ""),
        }


# ---------------------------------------------------------------------------
# Aggregate SignalIntelligence facade
# ---------------------------------------------------------------------------


class SignalIntelligence:
    """Single facade that owns all JS-1.x + Phase 6 components."""

    def __init__(self) -> None:
        from wallet_manager.strategies.model_registry import get_model_registry

        self.ic_tracker = ICTracker()
        self.ir_tracker = SignalIRTracker()           # Phase 6
        self.decay_analyzer = SignalDecayAnalyzer()
        self.correlation_matrix = SignalCorrelationMatrix()
        self.diversity_score = EnsembleDiversityScore()
        self.retirement_store = SignalRetirementStore()
        self._scorecard = SignalScorecard(            # Phase 6
            self.ic_tracker,
            self.ir_tracker,
            self.decay_analyzer,
            model_registry=get_model_registry(),
            retirement_store=self.retirement_store,
        )
        self._cycle_count = 0
        self._ir_snapshot_every = 50   # snapshot IR every N cycles

    def record_cycle(
        self,
        *,
        robust_alpha: float,
        confidence: float,
        adf_pvalue: float,
        garch_sigma: float,
        spread_bps: float,
        current_price: float,
        signal_direction: int = 0,
    ) -> None:
        """Call once per shadow cycle to feed all components."""
        self.ic_tracker.record_signal("robust_alpha", robust_alpha, current_price)
        self.ic_tracker.record_signal("confidence", confidence, current_price)
        self.ic_tracker.record_signal("adf_pvalue", adf_pvalue, current_price)
        self.ic_tracker.record_signal("garch_sigma", garch_sigma, current_price)
        self.correlation_matrix.record(robust_alpha, confidence, adf_pvalue, garch_sigma, spread_bps)
        if signal_direction != 0:
            self.decay_analyzer.record_signal(current_price, signal_direction)
        self.ic_tracker.resolve_pending(current_price)
        self.decay_analyzer.update(current_price)
        self._cycle_count += 1
        if self._cycle_count % self._ir_snapshot_every == 0:
            self.ir_tracker.snapshot(self.ic_tracker)
            self._scorecard.generate(persist_retirements=True)

    def record_model_predictions(
        self,
        xgboost: int,
        lightgbm: int,
        lstm: int,
        sklearn: int,
    ) -> None:
        self.diversity_score.record(xgboost, lightgbm, lstm, sklearn)

    def get_scorecard(self) -> dict[str, Any]:
        """Return the Phase 6 signal scorecard (IC + IR + decay + retirement)."""
        return self._scorecard.generate()

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": time.time(),
            "ic_report": self.ic_tracker.get_ic_report(),
            "ir_report": self.ir_tracker.get_ir_report(),     # Phase 6
            "scorecard": self.get_scorecard(),                 # Phase 6
            "recent_retirements": self.retirement_store.recent(limit=10),
            "decay_curve": self.decay_analyzer.get_decay_curve(),
            "correlation_matrix": self.correlation_matrix.get_matrix(),
            "ensemble_diversity": self.diversity_score.get_report(),
        }

    def get_alerts(self) -> list[str]:
        alerts: list[str] = []
        ic = self.ic_tracker.get_ic_report()
        for s in ic.get("alerts", []):
            alerts.append(f"IC_NOISE: signal '{s}' IC < 0.02, consider deactivating.")
        # Phase 6 — IR-based retirement alerts
        scorecard = self.get_scorecard()
        for s in scorecard.get("retire_now", []):
            if f"IC_NOISE: signal '{s}'" not in "".join(alerts):
                alerts.append(f"RETIRE_SIGNAL: signal '{s}' IR/IC below threshold — retire with evidence.")
        div = self.diversity_score.get_report()
        if div.get("alert"):
            alerts.append(f"LOW_DIVERSITY: ensemble diversity {div['diversity_score']:.3f} < 0.15.")
        corr = self.correlation_matrix.get_matrix()
        for pair in corr.get("redundant_pairs", []):
            alerts.append(f"REDUNDANT_SIGNALS: {pair['signal_a']} / {pair['signal_b']} corr={pair['correlation']:.2f}")
        return alerts


# ---------------------------------------------------------------------------
# Phase 6 — JS-1.5  Signal IR Tracker (Information Ratio = IC / std(IC))
# ---------------------------------------------------------------------------

_IR_WINDOW = 20   # rolling IC snapshots used to compute IR


class SignalIRTracker:
    """Tracks Information Ratio (IR) per signal.

    IR = mean(IC_window) / std(IC_window).

    A stable signal has IR > 0.5; an erratic signal has IR near 0 even when
    mean IC is positive.  IR exposes whether IC is *consistently* positive or
    just noisy.

    Works as a companion to ICTracker: call ``snapshot(ic_tracker)`` each
    evaluation period (e.g. daily or per N trades) to record the current IC
    for each signal.
    """

    def __init__(self, window: int = _IR_WINDOW) -> None:
        self._window = window
        # signal_name → deque of IC snapshots
        self._ic_history: dict[str, deque[float]] = {}

    def snapshot(self, ic_tracker: ICTracker) -> None:
        """Record one IC snapshot per signal from the current ICTracker state."""
        for signal_name in ic_tracker._resolved:
            ic = ic_tracker.compute_ic(signal_name)
            if signal_name not in self._ic_history:
                self._ic_history[signal_name] = deque(maxlen=self._window)
            self._ic_history[signal_name].append(ic)

    def compute_ir(self, signal_name: str) -> float:
        """Return IR for *signal_name*. Returns 0.0 if insufficient data."""
        history = list(self._ic_history.get(signal_name, []))
        if len(history) < 2:
            return 0.0
        n = len(history)
        mean_ic = sum(history) / n
        variance = sum((x - mean_ic) ** 2 for x in history) / (n - 1)
        std_ic = math.sqrt(variance) if variance > 0 else 0.0
        return mean_ic / std_ic if std_ic > 0 else 0.0

    def get_ir_report(self) -> dict[str, Any]:
        """Return IR for all tracked signals with retirement recommendations."""
        rows: list[dict[str, Any]] = []
        for name in self._ic_history:
            ir = self.compute_ir(name)
            history = list(self._ic_history[name])
            mean_ic = sum(history) / max(len(history), 1)
            rows.append({
                "signal": name,
                "ir": round(ir, 4),
                "mean_ic": round(mean_ic, 5),
                "n_snapshots": len(history),
                "status": self._ir_status(ir, mean_ic),
            })
        rows.sort(key=lambda r: r["ir"], reverse=True)
        return {
            "generated_at": time.time(),
            "window": self._window,
            "signals": rows,
            "retire_candidates": [
                r["signal"] for r in rows
                if r["status"] == "RETIRE" and r["n_snapshots"] >= 5
            ],
        }

    @staticmethod
    def _ir_status(ir: float, mean_ic: float) -> str:
        if mean_ic < 0.0:
            return "RETIRE"       # consistently negative IC
        if ir >= 0.5 and mean_ic >= 0.03:
            return "STRONG"
        if ir >= 0.25 or mean_ic >= 0.02:
            return "ACCEPTABLE"
        if mean_ic >= 0.01:
            return "WEAK"
        return "RETIRE"


# ---------------------------------------------------------------------------
# Phase 6 — Signal Scorecard (IC + IR + decay in one shot)
# ---------------------------------------------------------------------------


class SignalScorecard:
    """Unified Phase 6 scorecard: IC, IR, decay, and retirement recommendation.

    Answers the Phase 6 exit gate question:
    "Which signals and models are adding value?"

    Usage::

        scorecard = SignalScorecard(ic_tracker, ir_tracker, decay_analyzer)
        report = scorecard.generate()
        # report["retire_now"]  — signals to deactivate immediately
        # report["signals"]     — ranked scorecard rows
    """

    # IC below this threshold on N consecutive snapshots → retire
    IC_RETIRE_THRESHOLD = 0.01
    IR_RETIRE_THRESHOLD = 0.0

    def __init__(
        self,
        ic_tracker: ICTracker,
        ir_tracker: SignalIRTracker,
        decay_analyzer: SignalDecayAnalyzer,
        model_registry: Any | None = None,
        retirement_store: SignalRetirementStore | None = None,
    ) -> None:
        self._ic = ic_tracker
        self._ir = ir_tracker
        self._decay = decay_analyzer
        self._model_registry = model_registry
        self._retirement_store = retirement_store

    def generate(self, *, persist_retirements: bool = False) -> dict[str, Any]:
        """Produce the full signal scorecard."""
        ic_report = self._ic.get_ic_report()
        ir_report = self._ir.get_ir_report()
        decay = self._decay.get_decay_curve()
        model_attribution = self._build_model_attribution()

        # Build per-signal rows
        ir_by_name = {r["signal"]: r for r in ir_report["signals"]}
        ic_by_name = {r["signal"]: r for r in ic_report["signals"]}
        all_signals = set(ir_by_name) | set(ic_by_name)

        rows: list[dict[str, Any]] = []
        retire_now: list[str] = []
        retire_rows: list[dict[str, Any]] = []

        for name in all_signals:
            ic_row = ic_by_name.get(name, {"ic": 0.0, "n_observations": 0, "status": "UNKNOWN"})
            ir_row = ir_by_name.get(name, {"ir": 0.0, "mean_ic": 0.0, "n_snapshots": 0, "status": "UNKNOWN"})
            ic_val = ic_row["ic"]
            ir_val = ir_row["ir"]

            # Composite score: weighted sum of normalised IC and IR
            composite = round(0.6 * max(ic_val, 0.0) + 0.4 * max(ir_val, 0.0) / max(abs(ir_val), 0.01), 5)

            retirement_reason = ""
            should_retire = (
                ir_row["status"] == "RETIRE"
                or (ic_row["status"] == "NOISE"
                and ic_row["n_observations"] >= 20)
            )
            if should_retire:
                retire_now.append(name)
                retirement_reason = (
                    "NEGATIVE_OR_UNSTABLE_IR"
                    if ir_row["status"] == "RETIRE"
                    else "LOW_IC_WITH_SUFFICIENT_OBSERVATIONS"
                )

            row = {
                "signal": name,
                "ic": ic_val,
                "ir": ir_val,
                "ic_status": ic_row["status"],
                "ir_status": ir_row["status"],
                "n_observations": ic_row["n_observations"],
                "n_snapshots": ir_row.get("n_snapshots", 0),
                "composite_score": composite,
                "retire": should_retire,
                "retirement_reason": retirement_reason,
            }
            rows.append(row)
            if should_retire:
                retire_rows.append({
                    **row,
                    "recorded_at": time.time(),
                })

        rows.sort(key=lambda r: r["composite_score"], reverse=True)
        persisted_count = (
            self._retirement_store.persist_rows(retire_rows)
            if persist_retirements and self._retirement_store is not None
            else 0
        )
        models_adding_value = [
            row["model_id"]
            for row in model_attribution.get("models", [])
            if row.get("adding_value")
        ]

        return {
            "generated_at": time.time(),
            "signals": rows,
            "retire_now": list(set(retire_now)),
            "optimal_hold_minutes": decay.get("optimal_hold_minutes"),
            "decay_status": decay.get("status", "NO_DATA"),
            "pending_ic_observations": ic_report.get("pending_count", 0),
            "retirement_persisted_count": persisted_count,
            "model_attribution": model_attribution,
            "models_adding_value": models_adding_value,
        }

    def _build_model_attribution(self) -> dict[str, Any]:
        if self._model_registry and hasattr(self._model_registry, "get_attribution_report"):
            report = self._model_registry.get_attribution_report()
            if isinstance(report, Mapping):
                return dict(report)
        return {
            "generated_at": time.time(),
            "champion_model_id": None,
            "challenger_model_id": None,
            "should_promote": False,
            "models": [],
            "promotion_history_count": 0,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_signal_intel: SignalIntelligence | None = None


def get_signal_intelligence() -> SignalIntelligence:
    global _signal_intel
    if _signal_intel is None:
        _signal_intel = SignalIntelligence()
    return _signal_intel
