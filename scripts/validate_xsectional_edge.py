#!/usr/bin/env python3
"""scripts/validate_xsectional_edge.py — honest OOS test of CROSS-SECTIONAL momentum.

Faz 1 killed time-series (single-asset) momentum. Cross-sectional momentum is a
different, well-documented crypto factor (Liu, Tsyvinski & Wu 2022): each period,
rank a basket of coins by trailing return and hold the top-k. It is RELATIVE
ranking, not absolute market-timing — structurally more robust to the single-window
overfit that killed the stablecoin-supply signal (see docs/ONCHAIN_FINDINGS.md).

The fair benchmark for a cross-sectional long-only strategy is EQUAL-WEIGHT HOLD of
the same universe (not just BTC): we must beat "own the whole basket".

Honesty:
    * long-only top-k (realistic for a spot wallet — no shorting);
    * cost charged on rebalance turnover;
    * walk-forward per-fold consistency vs equal-weight hold;
    * date slicing (--from-ym/--to-ym) for true out-of-cycle (different period);
    * SURVIVORSHIP BIAS caveat: the universe is coins that survived to 2026
      (no LUNA/FTT/dead alts) => any positive result is an UPPER bound. A real
      edge must be large and consistent to survive this known optimistic bias.

Usage:
    python scripts/validate_xsectional_edge.py --lookback 30 --top-k 3 --rebal 7 \
        --cost-bps 25 --from-ym 2020-10 --to-ym 2026-06

Data: Binance daily klines (free, no auth), USDT pairs.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

import numpy as np

DAY = 86400
PERIODS_PER_YEAR = 365

# liquid universe with history from ~2020-09 (all present by 2020-10).
# NOTE: MATICUSDT excluded — Binance renamed it to POLUSDT in 2024-09, which
# would truncate the common-day intersection at that date.
UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT",
    "LTCUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "ATOMUSDT",
    "TRXUSDT", "ETCUSDT", "XLMUSDT", "EOSUSDT", "UNIUSDT",
]


def fetch_binance_daily_close(symbol: str) -> dict[int, float]:
    daily: dict[int, float] = {}
    start_ms = 1500000000000
    now_ms = int(time.time() * 1000)
    while start_ms < now_ms:
        url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}"
               f"&interval=1d&startTime={start_ms}&limit=1000")
        with urllib.request.urlopen(url, timeout=30) as resp:
            kl = json.loads(resp.read())
        if not kl:
            break
        for k in kl:
            daily[(int(k[0]) // 1000 // DAY) * DAY] = float(k[4])
        newest = max(int(k[0]) for k in kl)
        if len(kl) < 1000:
            break
        start_ms = newest + DAY * 1000
        time.sleep(0.15)
    return daily


def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std(ddof=1) < 1e-12:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR))


def cum(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    return float(np.prod(1 + r) - 1)


def ym_to_ts(ym: str) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, 0)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=30, help="trailing return window (days)")
    ap.add_argument("--top-k", type=int, default=3, help="number of coins held long")
    ap.add_argument("--rebal", type=int, default=7, help="rebalance interval (days)")
    ap.add_argument("--cost-bps", type=float, default=25.0, help="cost per unit turnover, bps")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--from-ym", default="")
    ap.add_argument("--to-ym", default="")
    ap.add_argument("--reversal", action="store_true",
                    help="falsification: hold BOTTOM-k instead of top-k")
    args = ap.parse_args()

    print(f"fetching {len(UNIVERSE)} symbols from Binance (daily) ...")
    series = {}
    for s in UNIVERSE:
        series[s] = fetch_binance_daily_close(s)
        time.sleep(0.05)

    # common day grid: days where ALL symbols have a price
    common = set.intersection(*[set(v) for v in series.values()])
    days = sorted(common)
    if args.from_ym:
        lo = ym_to_ts(args.from_ym); days = [d for d in days if d >= lo]
    if args.to_ym:
        hi = ym_to_ts(args.to_ym); days = [d for d in days if d <= hi]
    if len(days) < 200:
        print(f"FAIL: only {len(days)} common days.")
        return 1
    syms = list(UNIVERSE)
    P = np.array([[series[s][d] for s in syms] for d in days], dtype=float)  # [T, N]
    T, N = P.shape
    print(f"panel: {T} days x {N} coins  "
          f"({time.strftime('%Y-%m', time.gmtime(days[0]))} -> "
          f"{time.strftime('%Y-%m', time.gmtime(days[-1]))})")
    print(f"SURVIVORSHIP BIAS: universe = coins alive in 2026; results are an upper bound.")

    ret = np.full((T, N), np.nan)
    ret[1:] = P[1:] / P[:-1] - 1.0  # daily simple returns

    lb, k, rb = args.lookback, args.top_k, args.rebal
    cost = args.cost_bps / 1e4

    # strategy daily returns: pick top-k by trailing-lb return, hold for rb days
    strat = np.full(T, np.nan)
    ew = np.full(T, np.nan)        # equal-weight-hold benchmark (whole basket)
    prev_w = np.zeros(N)
    for t in range(lb, T - 1):
        ew[t + 1] = np.nanmean(ret[t + 1])
        if (t - lb) % rb == 0:  # rebalance day
            mom = P[t] / P[t - lb] - 1.0
            order = np.argsort(mom)
            chosen = order[:k] if args.reversal else order[-k:]
            w = np.zeros(N)
            w[chosen] = 1.0 / k
            turn = np.abs(w - prev_w).sum()
            prev_w = w
        else:
            turn = 0.0
        strat[t + 1] = float(np.nansum(prev_w * ret[t + 1])) - cost * turn

    s = strat[np.isfinite(strat)]
    e = ew[np.isfinite(ew)]
    btc = ret[:, 0][np.isfinite(ret[:, 0])]
    label = "REVERSAL(bottom-k)" if args.reversal else "MOMENTUM(top-k)"
    print(f"\n=== Cross-sectional {label}  lb={lb} k={k} rebal={rb} cost={args.cost_bps}bps ===")
    print(f"  STRATEGY        net = {cum(s)*100:+9.1f}%   Sharpe = {sharpe(s):+.3f}")
    print(f"  EQUAL-WT HOLD       = {cum(e)*100:+9.1f}%   Sharpe = {sharpe(e):+.3f}")
    print(f"  BTC HOLD            = {cum(btc)*100:+9.1f}%   Sharpe = {sharpe(btc):+.3f}")

    # walk-forward per-fold vs equal-weight hold (the fair benchmark)
    idx = np.where(np.isfinite(strat) & np.isfinite(ew))[0]
    folds = np.array_split(idx, args.folds)
    win = 0
    print("per-fold strategy vs equal-weight hold:")
    for i, f in enumerate(folds):
        sc, ec = cum(strat[f]), cum(ew[f])
        w = sc > ec; win += w
        t0 = time.strftime("%Y-%m", time.gmtime(days[f[0]]))
        t1 = time.strftime("%Y-%m", time.gmtime(days[f[-1]]))
        print(f"  fold {i} [{t0}->{t1}] strat={sc*100:+8.1f}%  ew={ec*100:+8.1f}%  {'WIN' if w else 'lose'}")
    print(f"folds beating equal-weight hold: {win}/{len(folds)}")

    beats = cum(s) > cum(e) and sharpe(s) > sharpe(e) and win > len(folds) / 2
    print("\n=== VERDICT ===")
    if beats and not args.reversal:
        print("PASS (in this slice): cross-sectional momentum beats equal-weight hold "
              "net of costs with majority fold consistency. RUN OUT-OF-CYCLE: confirm "
              "on a different period (--from-ym/--to-ym) before believing. Mind survivorship.")
    else:
        print("NO EDGE in this slice: does not beat equal-weight hold. "
              "Per CLAUDE.md PUSULA #3, log and move on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
