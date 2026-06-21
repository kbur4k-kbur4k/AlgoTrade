"""Regression: VirtualLedger.initialize() must migrate a pre-session_id DB.

Bug: on a database whose ``paper_decisions`` table predates the ``session_id``
column, ``initialize()`` raised ``OperationalError: no such column: session_id``
because the ``idx_pd_session`` index was created BEFORE the column-add
migration. The failure aborted engine init, so every paper cycle was skipped
and no paper trades were ever recorded.
"""
from __future__ import annotations

import sqlite3

from wallet_manager.strategies.paper_engine import VirtualLedger

# The pre-session_id paper_decisions schema (22 columns, no session_id).
_PRE_MIGRATION_DDL = """
CREATE TABLE paper_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL,
    wallet_id TEXT,
    cycle_phase TEXT,
    action TEXT,
    regime_label TEXT,
    setup_tag TEXT,
    decision_class TEXT,
    primary_reason TEXT,
    reason_codes TEXT,
    raw_alpha REAL,
    robust_alpha REAL,
    confidence REAL,
    adf_pvalue REAL,
    stationarity_d REAL,
    volatility_regime TEXT,
    risk_position_usd REAL,
    trade_budget_usd REAL,
    gas_cost_usd REAL,
    total_equity_usd REAL,
    pnl_usd REAL,
    notes TEXT
)
"""


def _make_pre_migration_db(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(_PRE_MIGRATION_DDL)
        conn.execute(
            "INSERT INTO paper_decisions (timestamp, wallet_id, action) VALUES (?, ?, ?)",
            (1.0, "w", "skip"),
        )
        conn.commit()
    finally:
        conn.close()


async def test_initialize_migrates_pre_session_id_db(tmp_path):
    """initialize() on a pre-session_id DB must succeed and add the column."""
    db = tmp_path / "old_paper.db"
    _make_pre_migration_db(str(db))

    # Pre-condition: session_id absent.
    conn = sqlite3.connect(str(db))
    pre_cols = [r[1] for r in conn.execute("PRAGMA table_info(paper_decisions)")]
    conn.close()
    assert "session_id" not in pre_cols

    ledger = VirtualLedger(db_path=str(db))
    try:
        # Was raising OperationalError: no such column: session_id
        await ledger.initialize()
    finally:
        await ledger.shutdown()

    # Post-condition: migration added session_id.
    conn = sqlite3.connect(str(db))
    post_cols = [r[1] for r in conn.execute("PRAGMA table_info(paper_decisions)")]
    conn.close()
    assert "session_id" in post_cols
