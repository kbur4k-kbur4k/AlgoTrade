#!/usr/bin/env python3
"""scripts/validate_sentiment_edge.py — honest OOS test of a SENTIMENT signal.

Fifth alpha class, a genuinely different data source (not price / funding / supply /
momentum): the crypto Fear & Greed Index (alternative.me, free, daily since 2018).

Hypothesis (classic contrarian): extreme FEAR -> oversold -> bullish forward;
extreme GREED -> overbought -> bearish. signal = -zscore(FNG); long when fearful.

This time out-of-cycle discipline is BUILT IN: the runner is meant to be executed
across BOTH assets (ETH, BTC) and BOTH period halves immediately. An in-window pass
means nothing on its own — see docs/ONCHAIN_FINDINGS.md for why (the stablecoin
signal looked great in-window and collapsed out-of-cycle).

Usage:
    python scripts/validate_sentiment_edge.py --asset eth --zwin 30 --cost-bps 20 \
        --long-only --from-ym 2018-02 --to-ym 2022-12

Data: alternative.me FNG (free) + Binance daily klines (free).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

import numpy as np

from scripts.validate_funding_edge import rolling_zscore, spearman_ic
from scripts.validate_onchain_edge import fetch_binance_daily_close

DAY = 86400
PERIODS_PER_YEAR = 365
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"


def fetch_fng() -> dict[int, float]:
    with urllib.request.urlopen(FNG_URL, timeout=30) as resp:
        d = json.loads(resp.read())
    out: dict[int, float] = {}
    for row in d["data"]:
        out[(int(row["timestamp"]) // DAY) * DAY] = float(row["value"])
    return out


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
    ap.add_argument("--asset", choices=["eth", "btc"], default="eth")
    ap.add_argument("--zwin", type=int, default=30, help="rolling zscore window")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--cost-bps", type=float, default=20.0)
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="only position when |zscore| > threshold")
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--raw", action="store_true",
                    help="use raw contrarian level -(FNG-50) instead of zscore")
    ap.add_argument("--from-ym", default="")
    ap.add_argument("--to-ym", default="")
    args = ap.parse_args()

    print("fetching Fear & Greed Index (free) ...")
    fng = fetch_fng()
    symbol = {"eth": "ETHUSDT", "btc": "BTCUSDT"}[args.asset]
    print(f"fetching {symbol} daily closes from Binance ...")
    px = fetch_binance_daily_close(symbol)

    common = sorted(set(fng) & set(px))
    if args.from_ym:
        lo = ym_to_ts(args.from_ym); common = [d for d in common if d >= lo]
    if args.to_ym:
        hi = ym_to_ts(args.to_ym); common = [d for d in common if d <= hi]
    if len(common) < 200:
        print(f"FAIL: only {len(common)} overlapping days.")
        return 1
    days = np.array(common, dtype=np.int64)
    f = np.array([fng[d] for d in common], dtype=float)
    price = np.array([px[d] for d in common], dtype=float)
    print(f"aligned days: {len(days)}  ({time.strftime('%Y-%m', time.gmtime(days[0]))} -> "
          f"{time.strftime('%Y-%m', time.gmtime(days[-1]))})  asset={args.asset.upper()}")

    # contrarian signal: fearful (low FNG) -> long
    if args.raw:
        sig = -(f - 50.0)
        z = sig.copy()
    else:
        z = rolling_zscore(f, args.zwin)
        sig = -z

    fwd = np.full(len(price), np.nan)
    fwd[:-1] = price[1:] / price[:-1] - 1.0

    ic_all, p_all = spearman_ic(sig, fwd)
    print(f"\noverall IC = {ic_all:+.4f} (p={p_all:.4f}, n={np.isfinite(sig*fwd).sum()})")

    idx = np.where(np.isfinite(sig) & np.isfinite(fwd))[0]
    folds = np.array_split(idx, args.folds)
    pos_folds = 0
    for k, fold in enumerate(folds):
        rho, p = spearman_ic(sig[fold], fwd[fold])
        pos_folds += rho > 0
    print(f"positive-IC folds: {pos_folds}/{len(folds)}")

    # cost-aware backtest vs buy-and-hold
    pos = np.zeros(len(sig))
    active = np.isfinite(z) & (np.abs(z) > args.threshold)
    pos[active] = np.sign(sig[active])
    if args.long_only:
        pos = np.clip(pos, 0.0, 1.0)
    cost = args.cost_bps / 1e4
    strat = np.full(len(price), np.nan)
    prev = 0.0
    for i in range(len(price)):
        if not np.isfinite(fwd[i]):
            continue
        strat[i] = pos[i] * fwd[i] - cost * abs(pos[i] - prev)
        prev = pos[i]

    s = strat[np.isfinite(strat)]
    bh = fwd[np.isfinite(fwd)]
    turns = int(np.sum(np.abs(np.diff(np.concatenate([[0.0], pos[np.isfinite(fwd)]]))) > 0))
    print(f"\n=== Backtest (cost={args.cost_bps}bps, thr={args.threshold}, "
          f"{'long-only' if args.long_only else 'long/short'}, turns={turns}) ===")
    print(f"  STRATEGY  net = {cum(s)*100:+8.1f}%   Sharpe = {sharpe(s):+.3f}")
    print(f"  BUY&HOLD      = {cum(bh)*100:+8.1f}%   Sharpe = {sharpe(bh):+.3f}")

    # per-fold strategy vs buy-hold
    win = 0
    print("per-fold strat vs buy-hold:")
    for k, fold in enumerate(folds):
        sc, bc = cum(strat[fold]), cum(fwd[fold])
        w = sc > bc; win += w
        t0 = time.strftime("%Y-%m", time.gmtime(days[fold[0]]))
        print(f"  fold {k} [{t0}] strat={sc*100:+7.1f}% bh={bc*100:+7.1f}% {'WIN' if w else 'lose'}")
    print(f"folds beating buy-hold: {win}/{len(folds)}")

    beats = cum(s) > cum(bh) and sharpe(s) > sharpe(bh) and win > len(folds) / 2
    print("\n=== VERDICT (this slice only — confirm across asset AND period) ===")
    print("PASS in slice" if beats else "NO EDGE in slice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
