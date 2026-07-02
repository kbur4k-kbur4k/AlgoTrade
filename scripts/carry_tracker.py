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

# ROADMAP.md FAZ C / T1: "carry 4+ hafta sürekli >%15/yıl" → operatöre bildirim.
# Proxy: trailing 28-day annualized mean funding above threshold, with enough
# settlement coverage that a few missing records can't fake a signal.
T1_WINDOW_DAYS = 28
T1_THRESHOLD_ANN = 0.15
T1_ALERT_FILE = "T1_ALERT.md"
SETTLEMENTS_PER_DAY = 3


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


def check_t1(
    con: sqlite3.Connection,
    window_days: int = T1_WINDOW_DAYS,
    threshold: float = T1_THRESHOLD_ANN,
) -> tuple[float, bool]:
    """Evaluate the T1 trigger: trailing-window annualized carry vs threshold.

    Returns (annualized_carry, fired). Never fires on thin data: requires at
    least half the expected settlements in the window, so gaps in recording
    cannot fabricate a fat-regime signal.
    """
    row = con.execute("SELECT MAX(funding_time) FROM carry_obs").fetchone()
    if not row or row[0] is None:
        return 0.0, False
    end = int(row[0])
    start = end - window_days * 86400 * 1000
    rates = [r[0] for r in con.execute(
        "SELECT funding_rate FROM carry_obs WHERE funding_time > ? AND funding_time <= ?",
        (start, end),
    )]
    expected = window_days * SETTLEMENTS_PER_DAY
    if len(rates) < expected / 2:
        return 0.0, False
    ann = (sum(rates) / len(rates)) * SETTLEMENTS_PER_DAY * 365
    return ann, ann > threshold


def write_t1_alert(ann: float, window_days: int = T1_WINDOW_DAYS) -> None:
    """Drop a loud, human-readable flag file for the operator (ROADMAP T1)."""
    with open(T1_ALERT_FILE, "w", encoding="utf-8") as f:
        f.write(
            "# 🔔 T1 ALERT — ŞİŞMAN CARRY REJİMİ\n\n"
            f"_{time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_\n\n"
            f"Son {window_days} günün yıllıklandırılmış funding carry'si: "
            f"**{ann*100:+.1f}%** (eşik: >{T1_THRESHOLD_ANN*100:.0f}%).\n\n"
            "ROADMAP.md FAZ C / T1 tetiklendi. Sıradaki adımlar OPERATÖRÜN:\n"
            "1. docs/CARRY_FINDINGS.md'yi oku (riskler: likidasyon/basis/karşı-taraf).\n"
            "2. Karar: türev hesabı + sermaye ayrılacak mı?\n"
            "3. Evetse: 2 hafta paper-doğrulama → ancak ondan sonra küçük pilot.\n\n"
            "Gerçek para OTOMATİK hareket etmez — bu dosya sadece bir zildir.\n"
        )


def main() -> int:
    con = sqlite3.connect(DB)
    ensure_db(con)
    # OneDrive altında sqlite: senkron nadiren yazım sırasında bozabilir — erken uyar.
    integ = con.execute("PRAGMA quick_check").fetchone()[0]
    if integ != "ok":
        print(f"WARN: {DB} integrity check failed: {integ} — yedekten dön/yeniden oluştur.")

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

    # ROADMAP FAZ C / T1: the watchtower's actual job — is the regime fat?
    t1_ann, fired = check_t1(con)
    if fired:
        write_t1_alert(t1_ann)
        print(f"\n*** T1 ALERT: trailing-{T1_WINDOW_DAYS}d carry {t1_ann*100:+.1f}%/yr "
              f"> {T1_THRESHOLD_ANN*100:.0f}% — {T1_ALERT_FILE} yazıldı, operatöre haber ver! ***")
    else:
        print(f"T1 check: trailing-{T1_WINDOW_DAYS}d carry {t1_ann*100:+.1f}%/yr "
              f"(eşik {T1_THRESHOLD_ANN*100:.0f}%) — rejim ince, nöbet sürüyor.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
