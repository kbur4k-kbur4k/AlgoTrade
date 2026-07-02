#!/usr/bin/env python3
"""scripts/market_recorder.py — the data-moat tape recorder (ROADMAP T5, free tier).

Medallion's real foundation was data nobody else kept (Straus's tick tapes).
The only moat available to us at ZERO cost is the same move: record what cannot
be downloaded later.

What Binance will NOT give you retroactively:
    * order-book depth      -> never available historically
    * open interest         -> public history capped at ~30 days
    * funding/mark snapshot -> funding rate is backfillable, mark-basis is not

So each run snapshots, for the top-N USDT perps by 24h volume:
    tape_funding : mark price + last funding rate (ALL symbols, 1 request)
    tape_depth   : top-20 bid/ask levels (per symbol)
    tape_oi      : open interest (per symbol)

Cost: $0. Runs alongside carry_tracker on the same 8h schedule (best-effort on
this machine — gaps happen when the PC sleeps; accepted trade for zero spend.
A 24/7 box only becomes justified if this data yields a signal that passes the
kill-test bar — money follows evidence).

Run once:
    python -m scripts.market_recorder
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request

DB = "market_tape.db"
TOP_N = 40
DEPTH_LEVELS = 20
FAPI = "https://fapi.binance.com"


def _get(path: str) -> object:
    with urllib.request.urlopen(f"{FAPI}{path}", timeout=20) as resp:
        return json.loads(resp.read())


def ensure_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS tape_funding (
            ts INTEGER, symbol TEXT, mark_price REAL, funding_rate REAL,
            PRIMARY KEY (ts, symbol)
        );
        CREATE TABLE IF NOT EXISTS tape_depth (
            ts INTEGER, symbol TEXT, bids TEXT, asks TEXT,
            PRIMARY KEY (ts, symbol)
        );
        CREATE TABLE IF NOT EXISTS tape_oi (
            ts INTEGER, symbol TEXT, open_interest REAL,
            PRIMARY KEY (ts, symbol)
        );
        """
    )
    con.commit()


def top_symbols(tickers: list[dict], n: int = TOP_N) -> list[str]:
    """Top-n USDT perps by 24h quote volume (dynamic universe, survivorship-free:
    we record whatever is big TODAY; delistings stay on the tape)."""
    usdt = [t for t in tickers if t.get("symbol", "").endswith("USDT")]
    usdt.sort(key=lambda t: float(t.get("quoteVolume", 0.0)), reverse=True)
    return [t["symbol"] for t in usdt[:n]]


def record_funding(con: sqlite3.Connection, ts: int, premium: list[dict],
                   universe: set[str]) -> int:
    n = 0
    for p in premium:
        s = p.get("symbol", "")
        if s not in universe:
            continue
        con.execute(
            "INSERT OR IGNORE INTO tape_funding VALUES (?,?,?,?)",
            (ts, s, float(p.get("markPrice", 0.0)), float(p.get("lastFundingRate", 0.0))),
        )
        n += 1
    con.commit()
    return n


def record_depth(con: sqlite3.Connection, ts: int, symbol: str, depth: dict) -> None:
    con.execute(
        "INSERT OR IGNORE INTO tape_depth VALUES (?,?,?,?)",
        (ts, symbol,
         json.dumps(depth.get("bids", [])[:DEPTH_LEVELS]),
         json.dumps(depth.get("asks", [])[:DEPTH_LEVELS])),
    )


def record_oi(con: sqlite3.Connection, ts: int, symbol: str, oi: dict) -> None:
    con.execute(
        "INSERT OR IGNORE INTO tape_oi VALUES (?,?,?)",
        (ts, symbol, float(oi.get("openInterest", 0.0))),
    )


def main() -> int:
    con = sqlite3.connect(DB)
    ensure_db(con)
    # OneDrive altında sqlite: senkron nadiren yazım sırasında bozabilir — erken uyar.
    integ = con.execute("PRAGMA quick_check").fetchone()[0]
    if integ != "ok":
        print(f"WARN: {DB} integrity check failed: {integ} — yedekten dön/yeniden oluştur.")
    ts = int(time.time())

    tickers = _get("/fapi/v1/ticker/24hr")
    symbols = top_symbols(tickers)
    premium = _get("/fapi/v1/premiumIndex")
    nf = record_funding(con, ts, premium, set(symbols))

    nd = no = 0
    for s in symbols:
        try:
            record_depth(con, ts, s, _get(f"/fapi/v1/depth?symbol={s}&limit={DEPTH_LEVELS}"))
            nd += 1
            record_oi(con, ts, s, _get(f"/fapi/v1/openInterest?symbol={s}"))
            no += 1
        except Exception as exc:  # one bad symbol must not kill the tape
            print(f"  warn: {s}: {exc}")
        time.sleep(0.15)  # stay far under rate limits
    con.commit()

    total = con.execute(
        "SELECT (SELECT COUNT(DISTINCT ts) FROM tape_depth), (SELECT COUNT(*) FROM tape_depth)"
    ).fetchone()
    print(f"tape @ {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(ts))}: "
          f"funding={nf} depth={nd} oi={no} symbols; "
          f"tape now holds {total[0]} snapshots / {total[1]} depth rows.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
