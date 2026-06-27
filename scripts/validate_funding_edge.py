#!/usr/bin/env python3
"""scripts/validate_funding_edge.py — honest OOS test of the FUNDING-RATE signal.

Faz 1 proved the OHLCV+LightGBM brain has no monetizable edge: the edge lives in
5-minute microstructure where trading costs kill it, and at long horizons (where
costs are fine) the price-derived edge vanishes. This script tests a *different*
alpha class in the unexplored quadrant: a NON-price, positioning signal at a
LONG (8-hour) horizon where costs are amortized.

Hypothesis (from wallet_manager/data/funding_rates.py):
    high positive perp funding  -> crowded longs  -> mean-reversion DOWN
    low / negative funding       -> crowded shorts -> squeeze UP
    => signal = -zscore(funding); long when funding cheap, short when crowded.

Data: Binance USDM perp ETHUSDT funding history (public, no auth). Each record
gives fundingRate and markPrice at the 8h settlement, so price alignment is free.

Honesty (mirrors Faz 1):
    * the zscore is causal (rolling, past-only) so IC is already out-of-sample;
    * we additionally report IC stability across walk-forward time folds;
    * we run a cost-aware long/short backtest and compare to buy-and-hold ETH.
      Costs: round-trip taker fee + slippage per position change, AND the funding
      actually paid/received each period (the real friction of this trade).

Usage:
    python scripts/validate_funding_edge.py --folds 6 --zwin 30 --cost-bps 5

Verdict rule (the ÖLÇÜ): the signal is a real, monetizable edge only if the
cost-aware equity curve beats buy-and-hold ETH on net return AND Sharpe, with
IC positive in a majority of OOS folds. Anything less = honest "no", next path.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

import numpy as np

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "ETHUSDT"
PERIODS_PER_YEAR = 3 * 365  # 3 settlements/day


def fetch_funding_history(symbol: str = SYMBOL, sleep: float = 0.25) -> list[dict]:
    """Page FORWARD through the full public funding history (1000/page).

    The endpoint ignores `limit` without a time anchor (returns only the last
    ~200), so we walk forward from a far-back startTime using the last
    fundingTime as the next cursor.
    """
    out: list[dict] = []
    start_time = 1567296000000  # 2019-09-01, before ETHUSDT perp listing
    while True:
        url = f"{BINANCE_FUNDING_URL}?symbol={symbol}&startTime={start_time}&limit=1000"
        with urllib.request.urlopen(url, timeout=20) as resp:
            batch = json.loads(resp.read())
        if not batch:
            break
        out.extend(batch)
        newest = max(int(b["fundingTime"]) for b in batch)
        if len(batch) < 1000:
            break
        start_time = newest + 1
        time.sleep(sleep)
        if len(out) > 20000:  # safety cap (~18 years)
            break
    # dedupe + sort ascending by fundingTime
    seen: dict[int, dict] = {}
    for b in out:
        seen[int(b["fundingTime"])] = b
    rows = [seen[k] for k in sorted(seen)]
    return rows


def rolling_zscore(x: np.ndarray, win: int) -> np.ndarray:
    """Causal rolling zscore: z[i] uses only x[i-win .. i] (past+current)."""
    z = np.full(len(x), np.nan)
    for i in range(len(x)):
        lo = max(0, i - win + 1)
        w = x[lo : i + 1]
        if len(w) < 5:
            continue
        mu = w.mean()
        sd = w.std(ddof=1)
        z[i] = (x[i] - mu) / sd if sd > 1e-12 else 0.0
    return z


def spearman_ic(sig: np.ndarray, fwd: np.ndarray) -> tuple[float, float]:
    """Spearman corr + two-sided p (via t-approx) on aligned, finite pairs."""
    from scipy.stats import spearmanr

    m = np.isfinite(sig) & np.isfinite(fwd)
    if m.sum() < 10:
        return float("nan"), float("nan")
    rho, p = spearmanr(sig[m], fwd[m])
    return float(rho), float(p)


def sharpe(returns: np.ndarray) -> float:
    r = returns[np.isfinite(returns)]
    if len(r) < 2 or r.std(ddof=1) < 1e-12:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--zwin", type=int, default=30, help="rolling zscore window")
    ap.add_argument(
        "--cost-bps",
        type=float,
        default=10.0,
        help="round-trip taker+slippage cost per position change, in bps. "
        "Binance ETHUSDT perp taker ~4bps/side => ~8bps round trip; 10 adds "
        "modest slippage. The signal only 'passes' at an unrealistic 5bps.",
    )
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="only take a position when |zscore| exceeds this (0 = always in)",
    )
    args = ap.parse_args()

    print(f"fetching {SYMBOL} funding history from Binance ...")
    rows = fetch_funding_history()
    if len(rows) < 200:
        print(f"FAIL: only {len(rows)} funding records — cannot test.")
        return 1

    ft = np.array([int(r["fundingTime"]) for r in rows], dtype=np.int64)
    rate = np.array([float(r["fundingRate"]) for r in rows], dtype=float)
    def _f(v: str) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    price = np.array([_f(r.get("markPrice", "")) for r in rows], dtype=float)
    # markPrice is blank/0 in old records — forward-fill, then back-fill the head
    for i in range(1, len(price)):
        if price[i] <= 0:
            price[i] = price[i - 1]
    first_valid = next((i for i, p in enumerate(price) if p > 0), 0)
    if first_valid > 0:
        ft, rate, price = ft[first_valid:], rate[first_valid:], price[first_valid:]
        print(f"trimmed {first_valid} leading records with no markPrice")

    span_days = (ft[-1] - ft[0]) / 1000 / 86400
    print(f"records: {len(rows)}  span: {span_days:.0f} days  "
          f"({time.strftime('%Y-%m', time.gmtime(ft[0]/1000))} -> "
          f"{time.strftime('%Y-%m', time.gmtime(ft[-1]/1000))})")

    # forward return over the next funding interval (the holding period)
    fwd = np.full(len(price), np.nan)
    fwd[:-1] = price[1:] / price[:-1] - 1.0

    # causal signal: high funding -> bearish => signal = -zscore
    z = rolling_zscore(rate, args.zwin)
    sig = -z

    # ---- IC overall + walk-forward fold stability -------------------------
    ic_all, p_all = spearman_ic(sig, fwd)
    print(f"\n=== Information Coefficient (signal vs next-period return) ===")
    print(f"overall IC = {ic_all:+.4f}  (p={p_all:.4f}, n={np.isfinite(sig*fwd).sum()})")

    idx = np.where(np.isfinite(sig) & np.isfinite(fwd))[0]
    folds = np.array_split(idx, args.folds)
    pos_folds = 0
    sig_folds = 0
    print("walk-forward folds:")
    for k, fold in enumerate(folds):
        rho, p = spearman_ic(sig[fold], fwd[fold])
        t0 = time.strftime("%Y-%m", time.gmtime(ft[fold[0]] / 1000))
        t1 = time.strftime("%Y-%m", time.gmtime(ft[fold[-1]] / 1000))
        flag = "+" if rho > 0 else "-"
        star = " *" if (p < 0.05) else ""
        if rho > 0:
            pos_folds += 1
        if p < 0.05:
            sig_folds += 1
        print(f"  fold {k} [{t0}->{t1}] n={len(fold):4d}  IC={rho:+.4f} p={p:.3f} {flag}{star}")
    print(f"positive-IC folds: {pos_folds}/{len(folds)}   significant(p<0.05): {sig_folds}/{len(folds)}")

    # ---- cost-aware long/short backtest vs buy-and-hold -------------------
    # position in {-1,0,+1}; enter only when |z| > threshold
    pos = np.zeros(len(sig))
    active = np.isfinite(z) & (np.abs(z) > args.threshold)
    pos[active] = np.sign(sig[active])

    cost = args.cost_bps / 1e4
    strat_ret = np.full(len(price), np.nan)
    prev_pos = 0.0
    for i in range(len(price)):
        if not np.isfinite(fwd[i]):
            continue
        p_i = pos[i]
        turn_cost = cost * abs(p_i - prev_pos)
        # funding friction: a long pays funding when rate>0 (and vice versa)
        funding_pay = p_i * (-rate[i])  # long earns -rate; short earns +rate
        strat_ret[i] = p_i * fwd[i] + funding_pay - turn_cost
        prev_pos = p_i

    sr = strat_ret[np.isfinite(strat_ret)]
    bh = fwd[np.isfinite(fwd)]
    strat_cum = float(np.prod(1 + sr) - 1)
    bh_cum = float(np.prod(1 + bh) - 1)
    n_turns = int(np.sum(np.abs(np.diff(np.concatenate([[0.0], pos[np.isfinite(fwd)]]))) > 0))

    print(f"\n=== Cost-aware backtest ({len(sr)} periods, "
          f"cost={args.cost_bps}bps/turn, thr={args.threshold}) ===")
    print(f"position changes: {n_turns}")
    print(f"  STRATEGY  net return = {strat_cum*100:+8.1f}%   Sharpe = {sharpe(sr):+.3f}")
    print(f"  BUY&HOLD      return = {bh_cum*100:+8.1f}%   Sharpe = {sharpe(bh):+.3f}")

    beats = (strat_cum > bh_cum) and (sharpe(sr) > sharpe(bh)) and (pos_folds > len(folds) / 2)
    print("\n=== VERDICT ===")
    if beats:
        print("PASS: funding signal beats buy-and-hold net of costs AND has majority "
              "positive OOS IC. Candidate edge — promote to deeper validation.")
    else:
        print("NO EDGE (honest): funding signal does NOT net-beat buy-and-hold ETH. "
              "Per CLAUDE.md PUSULA #3, log it and move to the next alpha source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
