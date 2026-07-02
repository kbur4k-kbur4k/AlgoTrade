"""Unit tests for scripts/market_recorder.py — the data-moat tape recorder."""
from __future__ import annotations

import json
import sqlite3

import pytest

from scripts.market_recorder import (
    ensure_db,
    record_depth,
    record_funding,
    record_oi,
    top_symbols,
)


@pytest.fixture()
def con() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    ensure_db(c)
    return c


class TestTopSymbols:
    def test_ranks_usdt_perps_by_quote_volume(self) -> None:
        tickers = [
            {"symbol": "AAAUSDT", "quoteVolume": "100"},
            {"symbol": "BBBUSDT", "quoteVolume": "300"},
            {"symbol": "CCCBUSD", "quoteVolume": "999"},  # not USDT — excluded
            {"symbol": "DDDUSDT", "quoteVolume": "200"},
        ]
        assert top_symbols(tickers, n=2) == ["BBBUSDT", "DDDUSDT"]


class TestRecording:
    def test_funding_filters_to_universe_and_is_idempotent(self, con) -> None:
        premium = [
            {"symbol": "ETHUSDT", "markPrice": "1500.5", "lastFundingRate": "0.0001"},
            {"symbol": "XXXUSDT", "markPrice": "1.0", "lastFundingRate": "0.0002"},
        ]
        n = record_funding(con, 1000, premium, {"ETHUSDT"})
        assert n == 1
        record_funding(con, 1000, premium, {"ETHUSDT"})  # same ts — no dupes
        rows = con.execute("SELECT * FROM tape_funding").fetchall()
        assert rows == [(1000, "ETHUSDT", 1500.5, 0.0001)]

    def test_depth_truncates_to_top_levels(self, con) -> None:
        depth = {"bids": [[str(i), "1"] for i in range(50)],
                 "asks": [[str(i), "1"] for i in range(50)]}
        record_depth(con, 1000, "ETHUSDT", depth)
        bids, asks = con.execute(
            "SELECT bids, asks FROM tape_depth WHERE ts=1000 AND symbol='ETHUSDT'"
        ).fetchone()
        assert len(json.loads(bids)) == 20
        assert len(json.loads(asks)) == 20

    def test_oi_recorded(self, con) -> None:
        record_oi(con, 1000, "ETHUSDT", {"openInterest": "12345.6"})
        assert con.execute("SELECT open_interest FROM tape_oi").fetchone()[0] == 12345.6
