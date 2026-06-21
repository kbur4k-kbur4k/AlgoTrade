"""
wallet_manager/data/feature_registry.py
=========================================
Phase 4 — Data Layer: Feature contracts and registry.

Every feature used in model training or inference must be registered here.
This provides:
- A single source of truth for feature definitions
- Stale-data detection (is this feature fresh enough to use?)
- Version tracking (if formula changes, bump version)
- Input/output contracts (what feeds into this feature, what range is output?)

Usage::

    registry = FeatureRegistry()
    await registry.initialize()

    spec = FeatureSpec(
        name="ofi_5m",
        description="Order Flow Imbalance over 5-minute window",
        formula="(upticks - downticks) / max(total_ticks, 1)",
        inputs=["ticks.direction"],
        output_type="float",
        output_range=(-1.0, 1.0),
        stale_after_seconds=300,
        version="1.0",
    )
    await registry.register(spec)
    spec = await registry.get("ofi_5m")
    print(spec.is_stale(last_computed_ts=time.time() - 400))  # True
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
CREATE TABLE IF NOT EXISTS feature_specs (
    name                TEXT    PRIMARY KEY,
    version             TEXT    NOT NULL,
    description         TEXT    NOT NULL DEFAULT '',
    formula             TEXT    NOT NULL DEFAULT '',
    inputs              TEXT    NOT NULL DEFAULT '[]',   -- JSON list of source fields
    output_type         TEXT    NOT NULL DEFAULT 'float',
    output_range_min    REAL,
    output_range_max    REAL,
    stale_after_seconds INTEGER NOT NULL DEFAULT 3600,
    created_at          REAL    NOT NULL,
    deprecated          INTEGER NOT NULL DEFAULT 0,
    notes               TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fs_deprecated ON feature_specs(deprecated);
"""


@dataclass
class FeatureSpec:
    """Contract describing a single feature.

    Attributes:
        name: Unique feature name, e.g. ``"ofi_5m"``, ``"garch_sigma"``.
        version: Semver string. Increment when formula or inputs change.
        description: Human-readable description of what this feature captures.
        formula: How the feature is computed (informational, not executable).
        inputs: Source fields this feature depends on.
        output_type: Python type name (``"float"``, ``"int"``, ``"bool"``).
        output_range: (min, max) valid range. None means unbounded.
        stale_after_seconds: Max age before this feature value is considered stale.
        created_at: Unix epoch when this spec was registered.
        deprecated: True if this feature is no longer used.
        notes: Free-text notes.
    """

    name: str
    version: str = "1.0"
    description: str = ""
    formula: str = ""
    inputs: list[str] = field(default_factory=list)
    output_type: str = "float"
    output_range: tuple[float, float] | None = None
    stale_after_seconds: int = 3600
    created_at: float = field(default_factory=time.time)
    deprecated: bool = False
    notes: str = ""

    def is_stale(self, last_computed_ts: float) -> bool:
        """Return True if the feature value is older than allowed."""
        return (time.time() - last_computed_ts) > self.stale_after_seconds

    def is_in_range(self, value: float) -> bool:
        """Return True if *value* is within the declared output range."""
        if self.output_range is None:
            return True
        lo, hi = self.output_range
        return lo <= value <= hi

    def summary(self) -> str:
        rng = f" range=[{self.output_range[0]}, {self.output_range[1]}]" if self.output_range else ""
        return (
            f"{self.name} v{self.version} ({self.output_type}){rng} "
            f"stale>{self.stale_after_seconds}s"
            f"{' [DEPRECATED]' if self.deprecated else ''}"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["inputs"] = json.dumps(d["inputs"])
        if d["output_range"] is not None:
            d["output_range_min"] = d["output_range"][0]
            d["output_range_max"] = d["output_range"][1]
        else:
            d["output_range_min"] = None
            d["output_range_max"] = None
        del d["output_range"]
        d["deprecated"] = int(d["deprecated"])
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> FeatureSpec:
        rng: tuple[float, float] | None = None
        if row.get("output_range_min") is not None and row.get("output_range_max") is not None:
            rng = (float(row["output_range_min"]), float(row["output_range_max"]))
        return cls(
            name=row["name"],
            version=row["version"],
            description=row.get("description", ""),
            formula=row.get("formula", ""),
            inputs=json.loads(row.get("inputs", "[]")),
            output_type=row.get("output_type", "float"),
            output_range=rng,
            stale_after_seconds=int(row.get("stale_after_seconds", 3600)),
            created_at=float(row["created_at"]),
            deprecated=bool(row.get("deprecated", 0)),
            notes=row.get("notes", ""),
        )


# ---------------------------------------------------------------------------
# Built-in feature specs — registered on first initialize()
# ---------------------------------------------------------------------------

_BUILTIN_SPECS: list[FeatureSpec] = [
    FeatureSpec(
        name="garch_sigma",
        version="1.0",
        description="GJR-GARCH(1,1) conditional volatility estimate",
        formula="GJR-GARCH fitted on log-returns, annualised",
        inputs=["candles.close"],
        output_type="float",
        output_range=(0.0, 5.0),
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="kalman_price",
        version="1.0",
        description="Kalman filter smoothed price estimate",
        formula="Linear Kalman filter on close price",
        inputs=["candles.close"],
        output_type="float",
        stale_after_seconds=60,
    ),
    FeatureSpec(
        name="ofi_5m",
        version="1.0",
        description="Order Flow Imbalance over 5-minute tick window",
        formula="(upticks - downticks) / max(total_ticks, 1)",
        inputs=["ticks.direction"],
        output_type="float",
        output_range=(-1.0, 1.0),
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="realized_vol_5m",
        version="1.0",
        description="Realised volatility over 5-minute window (annualised)",
        formula="std(log_returns) * sqrt(105120)",
        inputs=["candles.close"],
        output_type="float",
        output_range=(0.0, 10.0),
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="realized_vol_30m",
        version="1.0",
        description="Realised volatility over 30-minute window (annualised)",
        formula="std(log_returns_6bar) * sqrt(17520)",
        inputs=["candles.close"],
        output_type="float",
        output_range=(0.0, 10.0),
        stale_after_seconds=600,
    ),
    FeatureSpec(
        name="momentum_5",
        version="1.0",
        description="5-bar price momentum (log return)",
        formula="log(close_t / close_{t-5})",
        inputs=["candles.close"],
        output_type="float",
        output_range=(-2.0, 2.0),
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="momentum_30",
        version="1.0",
        description="30-bar price momentum (log return)",
        formula="log(close_t / close_{t-30})",
        inputs=["candles.close"],
        output_type="float",
        output_range=(-2.0, 2.0),
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="vol_regime",
        version="1.0",
        description="Volatility regime label from HMM/GJR-GARCH",
        formula="HMM 3-state (LOW_VOL, MEDIUM_VOL, HIGH_VOL) or GARCH threshold fallback",
        inputs=["garch_sigma", "candles.volume"],
        output_type="str",
        stale_after_seconds=300,
    ),
    FeatureSpec(
        name="kyle_lambda",
        version="1.0",
        description="Kyle lambda price-impact coefficient",
        formula="OLS regression: delta_price ~ signed_volume",
        inputs=["ticks.direction", "ticks.price"],
        output_type="float",
        output_range=(0.0, 1e6),
        stale_after_seconds=600,
    ),
    FeatureSpec(
        name="amihud_ratio",
        version="1.0",
        description="Amihud illiquidity ratio",
        formula="|return| / volume_usd",
        inputs=["candles.close", "candles.volume_usdc"],
        output_type="float",
        output_range=(0.0, 1e6),
        stale_after_seconds=600,
    ),
]


class FeatureRegistry:
    """Async SQLite-backed registry of FeatureSpec records.

    Shares the same DB as DatasetRegistry by default.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables and register built-in specs."""
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA_SQL)
            await db.commit()
        self._initialized = True

        # Register built-ins (INSERT OR IGNORE so user overrides are preserved)
        for spec in _BUILTIN_SPECS:
            await self._register_if_absent(spec)

        log.info("FeatureRegistry initialized at %s (%d built-ins)", self._db_path, len(_BUILTIN_SPECS))

    async def _register_if_absent(self, spec: FeatureSpec) -> None:
        d = spec.to_dict()
        cols = ", ".join(d.keys())
        placeholders = ", ".join("?" for _ in d)
        sql = f"INSERT OR IGNORE INTO feature_specs ({cols}) VALUES ({placeholders})"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(sql, list(d.values()))
            await db.commit()

    async def register(self, spec: FeatureSpec) -> None:
        """Insert or replace a FeatureSpec."""
        await self.initialize()
        d = spec.to_dict()
        cols = ", ".join(d.keys())
        placeholders = ", ".join("?" for _ in d)
        sql = f"INSERT OR REPLACE INTO feature_specs ({cols}) VALUES ({placeholders})"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(sql, list(d.values()))
            await db.commit()
        log.info("FeatureRegistry: registered %s", spec.summary())

    async def get(self, name: str) -> FeatureSpec | None:
        """Return a FeatureSpec by name, or None if not found."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM feature_specs WHERE name = ?", (name,)
            ) as cur:
                row = await cur.fetchone()
        return FeatureSpec.from_row(dict(row)) if row else None

    async def list_all(self, include_deprecated: bool = False) -> list[FeatureSpec]:
        """Return all registered feature specs."""
        await self.initialize()
        where = "" if include_deprecated else "WHERE deprecated = 0"
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM feature_specs {where} ORDER BY name"
            ) as cur:
                rows = await cur.fetchall()
        return [FeatureSpec.from_row(dict(r)) for r in rows]

    async def deprecate(self, name: str, reason: str = "") -> None:
        """Soft-delete a feature spec."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE feature_specs SET deprecated = 1, notes = ? WHERE name = ?",
                (reason, name),
            )
            await db.commit()
        log.info("FeatureRegistry: deprecated %s (%s)", name, reason)


# ---------------------------------------------------------------------------
# Feature Store — persisted computed feature values
# ---------------------------------------------------------------------------

_FEATURE_STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS computed_features (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       INTEGER NOT NULL,       -- Unix epoch of candle/tick
    feature_name    TEXT    NOT NULL,       -- must match feature_specs.name
    value           REAL    NOT NULL,
    dataset_id      TEXT    NOT NULL DEFAULT '',  -- DatasetManifest.dataset_id or ''
    computed_at     REAL    NOT NULL        -- wall-clock time of computation
);
CREATE INDEX IF NOT EXISTS idx_cf_ts     ON computed_features(timestamp);
CREATE INDEX IF NOT EXISTS idx_cf_name   ON computed_features(feature_name);
CREATE INDEX IF NOT EXISTS idx_cf_ds     ON computed_features(dataset_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cf_unique
    ON computed_features(timestamp, feature_name, dataset_id);
"""


class FeatureStore:
    """Lightweight persistence layer for computed feature values.

    Stores one row per (timestamp, feature_name, dataset_id) tuple so that
    features computed during a pipeline run can be reloaded for research
    replay without recomputation.

    Shares the same SQLite file as FeatureRegistry and DatasetRegistry.

    Usage::

        store = FeatureStore()
        await store.initialize()

        # Write a batch of features for one candle
        await store.write_batch(
            timestamp=1704067500,
            features={"garch_sigma": 0.0031, "momentum_5": 0.0012},
            dataset_id="ds_eth_5m_2024Q1_v1",
        )

        # Reload for research
        df = await store.load(
            feature_names=["garch_sigma", "momentum_5"],
            dataset_id="ds_eth_5m_2024Q1_v1",
        )
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create computed_features table if absent."""
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_FEATURE_STORE_SCHEMA)
            await db.commit()
        self._initialized = True
        log.info("FeatureStore initialized at %s", self._db_path)

    async def write_batch(
        self,
        timestamp: int,
        features: dict[str, float],
        dataset_id: str = "",
    ) -> None:
        """Persist a dict of {feature_name: value} for a single timestamp.

        Uses INSERT OR REPLACE so re-running the pipeline is idempotent.

        Args:
            timestamp: Unix epoch of the candle this feature describes.
            features: Mapping of feature name to computed float value.
            dataset_id: DatasetManifest ID this computation belongs to, or ''.
        """
        await self.initialize()
        now = time.time()
        rows = [
            (timestamp, name, value, dataset_id, now)
            for name, value in features.items()
        ]
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO computed_features "
                "(timestamp, feature_name, value, dataset_id, computed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            await db.commit()
        log.debug(
            "FeatureStore: wrote %d feature(s) at ts=%d dataset_id=%r",
            len(rows), timestamp, dataset_id,
        )

    async def load(
        self,
        feature_names: list[str] | None = None,
        dataset_id: str = "",
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Load persisted feature values.

        Args:
            feature_names: If provided, return only these features.
            dataset_id: Filter by dataset.  '' means all datasets.
            start_ts: Inclusive lower bound on timestamp.
            end_ts: Inclusive upper bound on timestamp.

        Returns:
            List of dicts with keys: timestamp, feature_name, value, dataset_id, computed_at.
        """
        await self.initialize()
        clauses: list[str] = []
        params: list[Any] = []

        if dataset_id:
            clauses.append("dataset_id = ?")
            params.append(dataset_id)
        if feature_names:
            placeholders = ", ".join("?" for _ in feature_names)
            clauses.append(f"feature_name IN ({placeholders})")
            params.extend(feature_names)
        if start_ts is not None:
            clauses.append("timestamp >= ?")
            params.append(start_ts)
        if end_ts is not None:
            clauses.append("timestamp <= ?")
            params.append(end_ts)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM computed_features {where} ORDER BY timestamp, feature_name"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def count(self, dataset_id: str = "") -> int:
        """Return the number of stored feature rows, optionally filtered by dataset."""
        await self.initialize()
        if dataset_id:
            sql = "SELECT COUNT(*) FROM computed_features WHERE dataset_id = ?"
            params: list[Any] = [dataset_id]
        else:
            sql = "SELECT COUNT(*) FROM computed_features"
            params = []
        async with aiosqlite.connect(self._db_path) as db, db.execute(sql, params) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0
