"""
wallet_manager/data/dataset_manifest.py
========================================
Phase 4 — Data Layer: Dataset versioning and registry.

Every dataset used for research or training must have a DatasetManifest entry.
This enables:
- Reproducible research (same dataset_id → same data)
- Audit trails (which dataset trained which model?)
- Data discovery (what datasets exist?)

Usage::

    registry = DatasetRegistry()
    await registry.initialize()

    manifest = DatasetManifest(
        dataset_id="ds_eth_5m_2024Q1_v1",
        version="1.0.0",
        data_start_ts=1704067200,
        data_end_ts=1711929600,
        row_count=26208,
        source_priority=["uniswap_subgraph", "defillama", "binance"],
        preprocessing={"gap_fill_max_candles": 12, "spike_threshold_pct": 15.0},
        quality={"missing_pct": 0.3, "spike_count": 4, "stale_count": 0},
        checksum="sha256:abc123...",
    )
    await registry.register(manifest)

    loaded = await registry.get("ds_eth_5m_2024Q1_v1")
"""

from __future__ import annotations

import hashlib
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
CREATE TABLE IF NOT EXISTS dataset_manifests (
    dataset_id          TEXT    PRIMARY KEY,
    version             TEXT    NOT NULL,
    created_at          REAL    NOT NULL,
    data_start_ts       INTEGER NOT NULL,
    data_end_ts         INTEGER NOT NULL,
    row_count           INTEGER NOT NULL,
    source_priority     TEXT    NOT NULL,  -- JSON list
    preprocessing       TEXT    NOT NULL,  -- JSON dict
    quality             TEXT    NOT NULL,  -- JSON dict
    checksum            TEXT    NOT NULL,
    associated_models   TEXT    NOT NULL DEFAULT '[]',  -- JSON list
    associated_strategy TEXT    NOT NULL DEFAULT '',
    deprecated          INTEGER NOT NULL DEFAULT 0,
    notes               TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_dm_created ON dataset_manifests(created_at);
CREATE INDEX IF NOT EXISTS idx_dm_deprecated ON dataset_manifests(deprecated);
"""


@dataclass
class DatasetManifest:
    """Immutable record describing a versioned dataset.

    Attributes:
        dataset_id: Unique identifier, e.g. ``"ds_eth_5m_2024Q1_v1"``.
        version: Semver string, e.g. ``"1.0.0"``.
        data_start_ts: Unix epoch of first candle (seconds).
        data_end_ts: Unix epoch of last candle (seconds).
        row_count: Number of rows (candles) in the dataset.
        source_priority: Ordered list of data sources used.
        preprocessing: Preprocessing parameters applied (gap fill, spikes, etc.).
        quality: Quality metrics measured at creation time.
        checksum: SHA-256 hex digest of the dataset content.
        created_at: Unix epoch when this manifest was created.
        associated_models: List of model version IDs trained on this dataset.
        associated_strategy: Strategy name this dataset was built for.
        deprecated: True if this dataset should no longer be used.
        notes: Free-text notes.
    """

    dataset_id: str
    version: str
    data_start_ts: int
    data_end_ts: int
    row_count: int
    source_priority: list[str]
    preprocessing: dict[str, Any]
    quality: dict[str, Any]
    checksum: str
    created_at: float = field(default_factory=time.time)
    associated_models: list[str] = field(default_factory=list)
    associated_strategy: str = ""
    deprecated: bool = False
    notes: str = ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def duration_days(self) -> float:
        """Return the calendar span of this dataset in days."""
        return (self.data_end_ts - self.data_start_ts) / 86_400

    def summary(self) -> str:
        """One-line human-readable summary."""
        return (
            f"{self.dataset_id} v{self.version} "
            f"rows={self.row_count:,} "
            f"span={self.duration_days():.0f}d "
            f"{'[DEPRECATED]' if self.deprecated else ''}"
        ).strip()

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        """Return ``sha256:<hex>`` checksum for *data*."""
        digest = hashlib.sha256(data).hexdigest()
        return f"sha256:{digest}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_priority"] = json.dumps(d["source_priority"])
        d["preprocessing"] = json.dumps(d["preprocessing"])
        d["quality"] = json.dumps(d["quality"])
        d["associated_models"] = json.dumps(d["associated_models"])
        d["deprecated"] = int(d["deprecated"])
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DatasetManifest:
        return cls(
            dataset_id=row["dataset_id"],
            version=row["version"],
            created_at=float(row["created_at"]),
            data_start_ts=int(row["data_start_ts"]),
            data_end_ts=int(row["data_end_ts"]),
            row_count=int(row["row_count"]),
            source_priority=json.loads(row["source_priority"]),
            preprocessing=json.loads(row["preprocessing"]),
            quality=json.loads(row["quality"]),
            checksum=row["checksum"],
            associated_models=json.loads(row.get("associated_models", "[]")),
            associated_strategy=row.get("associated_strategy", ""),
            deprecated=bool(row.get("deprecated", 0)),
            notes=row.get("notes", ""),
        )


class DatasetRegistry:
    """Async SQLite-backed registry of DatasetManifest records.

    Args:
        db_path: Path to the SQLite registry file.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if they do not exist."""
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA_SQL)
            await db.commit()
        self._initialized = True
        log.info("DatasetRegistry initialized at %s", self._db_path)

    async def register(self, manifest: DatasetManifest) -> None:
        """Insert or replace a DatasetManifest.

        Args:
            manifest: The manifest to register.
        """
        await self.initialize()
        d = manifest.to_dict()
        cols = ", ".join(d.keys())
        placeholders = ", ".join("?" for _ in d)
        sql = f"INSERT OR REPLACE INTO dataset_manifests ({cols}) VALUES ({placeholders})"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(sql, list(d.values()))
            await db.commit()
        log.info("DatasetRegistry: registered %s", manifest.summary())

    async def get(self, dataset_id: str) -> DatasetManifest | None:
        """Fetch a manifest by ID. Returns None if not found."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM dataset_manifests WHERE dataset_id = ?", (dataset_id,)
            ) as cur:
                row = await cur.fetchone()
        return DatasetManifest.from_row(dict(row)) if row else None

    async def list_all(self, include_deprecated: bool = False) -> list[DatasetManifest]:
        """Return all registered manifests, optionally including deprecated ones."""
        await self.initialize()
        where = "" if include_deprecated else "WHERE deprecated = 0"
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM dataset_manifests {where} ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
        return [DatasetManifest.from_row(dict(r)) for r in rows]

    async def deprecate(self, dataset_id: str, reason: str = "") -> None:
        """Soft-delete a dataset (mark deprecated, preserve for audit)."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE dataset_manifests SET deprecated = 1, notes = ? WHERE dataset_id = ?",
                (reason, dataset_id),
            )
            await db.commit()
        log.info("DatasetRegistry: deprecated %s (%s)", dataset_id, reason)

    async def add_model_association(self, dataset_id: str, model_version: str) -> None:
        """Record that *model_version* was trained on *dataset_id*."""
        await self.initialize()
        manifest = await self.get(dataset_id)
        if manifest is None:
            log.warning("DatasetRegistry: dataset %s not found for model association", dataset_id)
            return
        if model_version not in manifest.associated_models:
            manifest.associated_models.append(model_version)
            await self.register(manifest)
        log.debug("DatasetRegistry: %s associated with model %s", dataset_id, model_version)
