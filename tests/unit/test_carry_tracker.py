"""Unit tests for scripts/carry_tracker.py — the standing watchtower recorder.

The tracker runs unattended on a schedule (ROADMAP.md FAZ B), so its recording
logic must be provably correct and idempotent: re-running on overlapping data
must never double-count carry.
"""
from __future__ import annotations

import sqlite3

import pytest

from scripts.carry_tracker import ENTRY_COST_BPS, NOTIONAL, ensure_db, record_settlements


@pytest.fixture()
def con() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    ensure_db(c)
    return c


def _rows(*pairs: tuple[int, float]) -> list[dict]:
    return [{"fundingTime": ft, "fundingRate": rate} for ft, rate in pairs]


class TestRecordSettlements:
    def test_entry_cost_applied_once_then_carry_accrues(self, con) -> None:
        new = record_settlements(con, _rows((1000, 0.0001), (2000, 0.0002)))
        assert new == 2
        entry = -(ENTRY_COST_BPS / 1e4) * NOTIONAL
        rows = con.execute(
            "SELECT funding_time, carry_usd, cum_carry_usd, note FROM carry_obs ORDER BY funding_time"
        ).fetchall()
        assert rows[0][1] == pytest.approx(0.0001 * NOTIONAL)
        assert rows[0][2] == pytest.approx(entry + 0.0001 * NOTIONAL)
        assert rows[0][3] == "entry_cost_applied"
        assert rows[1][2] == pytest.approx(entry + (0.0001 + 0.0002) * NOTIONAL)
        assert rows[1][3] == ""

    def test_idempotent_no_double_count(self, con) -> None:
        record_settlements(con, _rows((1000, 0.0001), (2000, 0.0002)))
        again = record_settlements(con, _rows((1000, 0.0001), (2000, 0.0002)))
        assert again == 0
        assert con.execute("SELECT COUNT(*) FROM carry_obs").fetchone()[0] == 2

    def test_overlapping_batch_appends_only_new(self, con) -> None:
        record_settlements(con, _rows((1000, 0.0001), (2000, 0.0002)))
        new = record_settlements(con, _rows((2000, 0.0002), (3000, -0.0001)))
        assert new == 1
        last = con.execute(
            "SELECT carry_usd, cum_carry_usd, note FROM carry_obs ORDER BY funding_time DESC LIMIT 1"
        ).fetchone()
        # negative funding = the short perp PAYS: carry goes down, entry cost not re-applied
        assert last[0] == pytest.approx(-0.0001 * NOTIONAL)
        entry = -(ENTRY_COST_BPS / 1e4) * NOTIONAL
        assert last[1] == pytest.approx(entry + (0.0001 + 0.0002 - 0.0001) * NOTIONAL)
        assert last[2] == ""

    def test_unsorted_input_recorded_in_time_order(self, con) -> None:
        record_settlements(con, _rows((3000, 0.0003), (1000, 0.0001), (2000, 0.0002)))
        times = [r[0] for r in con.execute(
            "SELECT funding_time FROM carry_obs ORDER BY rowid"
        )]
        assert times == [1000, 2000, 3000]
