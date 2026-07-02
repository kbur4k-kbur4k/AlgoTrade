#!/usr/bin/env python3
"""scripts/carry_tracker.py — forward paper-track of the delta-neutral carry candidate.

The edge search converged on ONE survivor: delta-neutral funding carry (see
docs/CARRY_FINDINGS.md). It is real but decaying (~3.3%/yr recently, ~risk-free).
Before anything real (which needs operator approval + derivatives infra), we must
PROVE it FORWARD — does the historical carry persist out-of-sample, in real time?

This script is the honest forward-tracker:
    * fetches the latest Binance ETHUSDT perp funding (free, no auth);
    * records each new 8h settlement and the simulated market-neutral carry accrual
      (funding received on a notional, minus an amortized cost assumption) to
      carry_track.db;
    * accumulates a running forward equity curve and annualized net.

It is PAPER ONLY: no orders, no keys, no real money — just recording what a neutral
book WOULD have earned. Costs nothing to run (pure HTTP + sqlite), so it is safe to
schedule every 8h (see scripts/setup_carry_schedule.* / STATUS.md) as the CLAUDE.md
continuity mechanism without burning API budget.

Run once:
    python -m scripts.carry_tracker
"""
from __future__ import annotations

import sqlite3
import sys
import time
import urllib.request
import json

DB = "carry_track.db"
NOTIONAL = 10_000.0          # paper notional (USD) for the neutral book
ENTRY_COST_BPS = 8.0         # one-time round-trip cost assumed when the book opens
SYMBOL = "ETHUSDT"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def ensure_db(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS carry_obs (
            funding_time INTEGER PRIMARY KEY,  -- ms, the 8h settlement
            recorded_at  REAL,
            funding_rate REAL,
            carry_usd    REAL,                 -- funding received on NOTIONAL this settlement
            cum_carry_usd REAL,                -- running total net of one-time entry cost
            note         TEXT
        )"""
    )
    con.commit()


def fetch_recent_funding(limit: int = 200) -> list[dict]:
    url = f"{FUNDING_URL}?symbol={SYMBOL}&limit={limit}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def record_settlements(con: sqlite3.Connection, rows: list[dict]) -> int:
    """Idempotently record new settlements; returns how many were new.

    Cumulative carry starts at -entry_cost (paid once when the book opens) and
    accrues fundingRate * NOTIONAL per settlement (short perp receives when >0).
    """
    existing = {r[0] for r in con.execute("SELECT funding_time FROM carry_obs")}
    last_cum = con.execute(
        "SELECT cum_carry_usd FROM carry_obs ORDER BY funding_time DESC LIMIT 1"
    ).fetchone()
    cum = last_cum[0] if last_cum else -(ENTRY_COST_BPS / 1e4) * NOTIONAL  # pay entry once
    first_record = last_cum is None

    new = 0
    for r in sorted(rows, key=lambda x: int(x["fundingTime"])):
        ft = int(r["fundingTime"])
        if ft in existing:
            continue
        rate = float(r["fundingRate"])
        carry = rate * NOTIONAL  # short perp receives funding when rate>0
        cum += carry
        con.execute(
            "INSERT OR IGNORE INTO carry_obs VALUES (?,?,?,?,?,?)",
            (ft, time.time(), rate, carry, cum,
             "entry_cost_applied" if first_record and new == 0 else ""),
        )
        new += 1
    con.commit()
    return new


def main() -> int:
    con = sqlite3.connect(DB)
    ensure_db(con)

    rows = fetch_recent_funding()
    if not rows:
        print("no funding data returned; nothing recorded.")
        return 1

    new = record_settlements(con, rows)

    # report running forward stats
    obs = con.execute(
        "SELECT funding_time, funding_rate, cum_carry_usd FROM carry_obs ORDER BY funding_time"
    ).fetchall()
    n = len(obs)
    if n >= 2:
        span_days = (obs[-1][0] - obs[0][0]) / 1000 / 86400
        net = obs[-1][2]
        ann = (net / NOTIONAL) / max(span_days / 365, 1e-9)
        print(f"recorded {new} new settlement(s); total tracked: {n}")
        print(f"forward span: {span_days:.1f}d | cum net carry: ${net:,.2f} "
              f"({net/NOTIONAL*100:+.2f}% on ${NOTIONAL:,.0f}) | annualized {ann*100:+.1f}%")
        print(f"(paper, market-neutral; benchmark risk-free ~+4-5%/yr; see docs/CARRY_FINDINGS.md)")
    else:
        print(f"recorded {new} settlement(s); need >=2 observations to report a curve.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
