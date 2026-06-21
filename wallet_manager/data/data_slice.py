"""
wallet_manager/data/data_slice.py
===================================
Phase 4 — Data Layer: Replayable data windows.

A DataSlice represents a named, bounded window of data within a dataset.
Slices enable:
- Deterministic train/test splits (same slice_id → same rows)
- Walk-forward epoch tracking (which candles were in fold 3?)
- Backtest replay from a specific historical window

Usage::

    registry = SliceRegistry()
    await registry.initialize()

    sl = DataSlice(
        slice_id="slice_train_2024Q1",
        dataset_id="ds_eth_5m_2024Q1_v1",
        purpose="train",
        start_ts=1704067200,
        end_ts=1711929600,
        row_count=18000,
    )
    await registry.register(sl)

    # Retrieve and replay
    sl = await registry.get("slice_train_2024Q1")
    print(sl.duration_days())
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import aiosqlite

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)

_DEFAULT_DB = os.getenv("DATASET_REGISTRY_DB_PATH", "dataset_registry.db")

SlicePurpose = Literal["train", "test", "validation", "backtest", "live_shadow", "other"]

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS data_slices (
    slice_id        TEXT    PRIMARY KEY,
    dataset_id      TEXT    NOT NULL,
    purpose         TEXT    NOT NULL,
    start_ts        INTEGER NOT NULL,
    end_ts          INTEGER NOT NULL,
    row_count       INTEGER NOT NULL,
    fold_index      INTEGER NOT NULL DEFAULT -1,
    created_at      REAL    NOT NULL,
    associated_models TEXT  NOT NULL DEFAULT '[]',
    notes           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ds_dataset ON data_slices(dataset_id);
CREATE INDEX IF NOT EXISTS idx_ds_purpose ON data_slices(purpose);
CREATE INDEX IF NOT EXISTS idx_ds_created ON data_slices(created_at);
"""


@dataclass
class DataSlice:
    """A bounded, labeled window of data from a parent dataset.

    Attributes:
        slice_id: Unique identifier, e.g. ``"slice_train_2024Q1_fold2"``.
        dataset_id: Parent DatasetManifest ID.
        purpose: How this slice is used (train / test / validation / backtest).
        start_ts: Unix epoch of first row in slice (seconds).
        end_ts: Unix epoch of last row in slice (seconds).
        row_count: Number of rows in this slice.
        fold_index: Walk-forward fold number (-1 = not part of WF split).
        created_at: Unix epoch when slice was created.
        associated_models: Models trained/evaluated on this slice.
        notes: Free-text notes.
    """

    slice_id: str
    dataset_id: str
    purpose: SlicePurpose
    start_ts: int
    end_ts: int
    row_count: int
    fold_index: int = -1
    created_at: float = field(default_factory=time.time)
    associated_models: list[str] = field(default_factory=list)
    notes: str = ""

    def duration_days(self) -> float:
        """Return the calendar span of this slice in days."""
        return (self.end_ts - self.start_ts) / 86_400

    def summary(self) -> str:
        fold = f" fold={self.fold_index}" if self.fold_index >= 0 else ""
        return (
            f"{self.slice_id} [{self.purpose}]{fold} "
            f"rows={self.row_count:,} span={self.duration_days():.0f}d"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["associated_models"] = json.dumps(d["associated_models"])
        return d

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DataSlice:
        return cls(
            slice_id=row["slice_id"],
            dataset_id=row["dataset_id"],
            purpose=row["purpose"],
            start_ts=int(row["start_ts"]),
            end_ts=int(row["end_ts"]),
            row_count=int(row["row_count"]),
            fold_index=int(row.get("fold_index", -1)),
            created_at=float(row["created_at"]),
            associated_models=json.loads(row.get("associated_models", "[]")),
            notes=row.get("notes", ""),
        )


class SliceRegistry:
    """Async SQLite-backed registry of DataSlice records.

    Shares the same DB as DatasetRegistry (dataset_registry.db) by default.
    """

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
        log.info("SliceRegistry initialized at %s", self._db_path)

    async def register(self, sl: DataSlice) -> None:
        """Insert or replace a DataSlice."""
        await self.initialize()
        d = sl.to_dict()
        cols = ", ".join(d.keys())
        placeholders = ", ".join("?" for _ in d)
        sql = f"INSERT OR REPLACE INTO data_slices ({cols}) VALUES ({placeholders})"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(sql, list(d.values()))
            await db.commit()
        log.info("SliceRegistry: registered %s", sl.summary())

    async def get(self, slice_id: str) -> DataSlice | None:
        """Fetch a slice by ID. Returns None if not found."""
        await self.initialize()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM data_slices WHERE slice_id = ?", (slice_id,)
            ) as cur:
                row = await cur.fetchone()
        return DataSlice.from_row(dict(row)) if row else None

    async def list_by_dataset(
        self, dataset_id: str, purpose: SlicePurpose | None = None
    ) -> list[DataSlice]:
        """Return all slices for a dataset, optionally filtered by purpose."""
        await self.initialize()
        if purpose:
            sql = "SELECT * FROM data_slices WHERE dataset_id = ? AND purpose = ? ORDER BY start_ts"
            args: tuple[str, ...] = (dataset_id, purpose)
        else:
            sql = "SELECT * FROM data_slices WHERE dataset_id = ? ORDER BY start_ts"
            args = (dataset_id,)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, args) as cur:
                rows = await cur.fetchall()
        return [DataSlice.from_row(dict(r)) for r in rows]

    async def list_walk_forward_folds(
        self, dataset_id: str
    ) -> list[tuple[DataSlice, DataSlice]]:
        """Return (train_slice, test_slice) pairs ordered by fold_index.

        Only returns complete pairs (both train and test exist for a fold).
        """
        await self.initialize()
        trains = {s.fold_index: s for s in await self.list_by_dataset(dataset_id, "train") if s.fold_index >= 0}
        tests = {s.fold_index: s for s in await self.list_by_dataset(dataset_id, "test") if s.fold_index >= 0}
        pairs = []
        for fold in sorted(set(trains) & set(tests)):
            pairs.append((trains[fold], tests[fold]))
        return pairs

    async def add_model_association(self, slice_id: str, model_version: str) -> None:
        """Record that *model_version* was trained/evaluated on *slice_id*."""
        await self.initialize()
        sl = await self.get(slice_id)
        if sl is None:
            log.warning("SliceRegistry: slice %s not found for model association", slice_id)
            return
        if model_version not in sl.associated_models:
            sl.associated_models.append(model_version)
            await self.register(sl)
        log.debug("SliceRegistry: %s associated with model %s", slice_id, model_version)
