#!/usr/bin/env python3
"""scripts/validate_carry_edge.py — delta-neutral funding CARRY (cash-and-carry).

Every prior attempt (price-ML, funding mean-reversion, on-chain supply, x-sectional
momentum, sentiment) was a DIRECTIONAL bet — predict price, beat buy-and-hold. All
died to market efficiency + costs + survivorship. This is categorically different:
a MARKET-NEUTRAL carry that harvests structural yield WITHOUT predicting direction.

Trade: long spot ETH + short equal-notional perp ETH.
    * price moves cancel (spot gain == perp loss and vice versa) -> delta-neutral;
    * while the short perp is open you RECEIVE funding when fundingRate > 0
      (perp longs pay shorts). Crypto perp funding is positive most of the time
      (perpetual premium) -> a positive carry.
P&L per 8h settlement (on notional) = fundingRate[t]  (received if you are short perp)
                                      - any rebalance/entry/exit cost.

This does NOT need to beat buy-and-hold ETH directionally. The right benchmark is the
RISK-FREE rate (~4-5%/yr): a market-neutral book should beat cash on a risk-adjusted
basis to be worth running.

Honesty:
    * net of a realistic round-trip cost amortized over the holding period;
    * "smart" variant only holds carry when recent funding > a hurdle (skip negative);
    * out-of-cycle: report per-period (--from-ym/--to-ym) so a single regime can't flatter it;
    * CAVEATS (printed): ignores liquidation risk, perp/spot basis slippage on entry,
      borrow limits, and exchange/counterparty risk. Real net is lower. PAPER ONLY.

Usage:
    python scripts/validate_carry_edge.py --cost-bps 8 --hurdle 0.0

Data: Binance USDM perp ETHUSDT funding history (free, no auth).
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from scripts.validate_funding_edge import fetch_funding_history

PERIODS_PER_YEAR = 3 * 365  # 8h settlements


def sharpe(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std(ddof=1) < 1e-12:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR))


def ym_to_ts(ym: str) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, 0)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost-bps", type=float, default=8.0,
                    help="round-trip cost to open/close BOTH legs, bps, per position change")
    ap.add_argument("--hurdle", type=float, default=0.0,
                    help="'smart' carry: only hold when trailing-avg funding > this (per 8h). "
                    "0.0 = always-on carry.")
    ap.add_argument("--hurdle-win", type=int, default=9, help="trailing window (8h units) for hurdle")
    ap.add_argument("--from-ym", default="")
    ap.add_argument("--to-ym", default="")
    ap.add_argument("--folds", type=int, default=6)
    args = ap.parse_args()

    print("fetching ETHUSDT funding history (free) ...")
    rows = fetch_funding_history()
    ft = np.array([int(r["fundingTime"]) // 1000 for r in rows], dtype=np.int64)
    rate = np.array([float(r["fundingRate"]) for r in rows], dtype=float)

    keep = np.ones(len(ft), dtype=bool)
    if args.from_ym:
        keep &= ft >= ym_to_ts(args.from_ym)
    if args.to_ym:
        keep &= ft <= ym_to_ts(args.to_ym)
    ft, rate = ft[keep], rate[keep]
    if len(rate) < 200:
        print(f"FAIL: only {len(rate)} settlements in window.")
        return 1
    span_days = (ft[-1] - ft[0]) / 86400
    print(f"settlements: {len(rate)}  span: {span_days:.0f}d  "
          f"({time.strftime('%Y-%m', time.gmtime(ft[0]))} -> "
          f"{time.strftime('%Y-%m', time.gmtime(ft[-1]))})")
    print(f"mean funding/8h = {rate.mean()*100:.4f}%  => naive annualized = "
          f"{rate.mean()*PERIODS_PER_YEAR*100:.1f}%  | positive settlements: "
          f"{(rate>0).mean()*100:.0f}%")

    cost = args.cost_bps / 1e4

    # position in {0,1}: 1 = carry on (short perp, long spot). Smart hurdle skips lulls.
    pos = np.ones(len(rate))
    if args.hurdle > 0:
        avg = np.full(len(rate), np.nan)
        for i in range(len(rate)):
            lo = max(0, i - args.hurdle_win + 1)
            avg[i] = rate[lo:i + 1].mean()
        pos = (avg > args.hurdle).astype(float)

    pnl = np.zeros(len(rate))
    prev = 0.0
    for i in range(len(rate)):
        # carry earns the funding rate while short the perp (received when rate>0)
        pnl[i] = pos[i] * rate[i] - cost * abs(pos[i] - prev)
        prev = pos[i]

    ann = pnl.mean() * PERIODS_PER_YEAR
    cum = float(np.prod(1 + pnl) - 1)
    in_mkt = pos.mean()
    turns = int(np.sum(np.abs(np.diff(np.concatenate([[0.0], pos]))) > 0))
    print(f"\n=== Delta-neutral carry (cost={args.cost_bps}bps, hurdle={args.hurdle}, "
          f"in-market {in_mkt*100:.0f}%, {turns} entries) ===")
    print(f"  NET annualized return = {ann*100:+.1f}%   (market-neutral)")
    print(f"  NET cumulative        = {cum*100:+.1f}%   over {span_days/365:.1f}y")
    print(f"  Sharpe (neutral book) = {sharpe(pnl):+.2f}")
    print(f"  benchmark risk-free   ~ +4 to +5%/yr")

    # out-of-cycle consistency: per-fold annualized net
    folds = np.array_split(np.arange(len(pnl)), args.folds)
    pos_folds = 0
    print("per-fold annualized net carry:")
    for k, f in enumerate(folds):
        a = pnl[f].mean() * PERIODS_PER_YEAR
        pos_folds += a > 0.05  # beats ~risk-free
        t0 = time.strftime("%Y-%m", time.gmtime(ft[f[0]]))
        t1 = time.strftime("%Y-%m", time.gmtime(ft[f[-1]]))
        print(f"  fold {k} [{t0}->{t1}]  net ann = {a*100:+6.1f}%  {'>rf' if a>0.05 else ''}")
    print(f"folds beating ~risk-free (>5%/yr): {pos_folds}/{len(folds)}")

    print("\nCAVEATS: ignores liquidation/basis-slippage/borrow-limit/counterparty risk; "
          "real net is lower. Needs a derivatives account => operator approval. PAPER ONLY.")
    good = ann > 0.05 and sharpe(pnl) > 0.5 and pos_folds > args.folds / 2
    print("\n=== VERDICT ===")
    if good:
        print("CANDIDATE: market-neutral carry clears risk-free with consistent positive "
              "folds. Different alpha class (yield, not prediction). Worth an out-of-cycle "
              "+ live-friction review with the operator before anything real.")
    else:
        print("WEAK/NO carry edge net of costs in this slice. Log honestly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
