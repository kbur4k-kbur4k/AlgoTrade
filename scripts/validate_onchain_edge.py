#!/usr/bin/env python3
"""scripts/validate_onchain_edge.py — honest OOS test of an ON-CHAIN macro signal.

Faz 1 left a gate open: "different alpha source (on-chain flow, alt-data)".
The intended CEX exchange-balance flow (wallet_manager/data/onchain_flows.py)
needs a paid CryptoCompare key (endpoint returns 401), so we test a free,
deep-history on-chain proxy from the same thesis: stablecoin supply as crypto
"dry powder".

Hypothesis:
    stablecoin total supply GROWING  -> new buying power entering crypto -> bullish ETH
    stablecoin supply CONTRACTING    -> capital leaving                  -> bearish ETH
    => signal = +zscore(stablecoin supply growth); long ETH when dry powder rises.

This is a NON-price signal at a LONG (daily) horizon — the quadrant where costs
are amortized and Faz 1's price-derived edge had vanished. Different alpha class.

Data (both free, no key):
    * stablecoin total circulating USD: DefiLlama stablecoins API (daily, since 2017)
    * ETH price: local historical_data.db candles resampled to daily close
      (no external price dependency; ~2023-2026 overlap)

Honesty (mirrors Faz 1 / validate_funding_edge):
    * zscore is causal (past-only) so IC is out-of-sample;
    * IC stability across walk-forward folds;
    * cost-aware long/short backtest vs buy-and-hold ETH.

Usage:
    python scripts/validate_onchain_edge.py --growth-win 7 --zwin 30 --cost-bps 10

Verdict (the ÖLÇÜ): real edge only if net-of-cost equity beats buy-and-hold on
return AND Sharpe, with majority positive OOS IC. Else honest "no", next path.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request

import numpy as np

# reuse the honest helpers from the funding kill-test
from scripts.validate_funding_edge import rolling_zscore, spearman_ic

DEFILLAMA_STABLES = "https://stablecoins.llama.fi/stablecoincharts/all"
DAY = 86400
PERIODS_PER_YEAR = 365  # daily horizon


def sharpe(returns: np.ndarray) -> float:
    r = returns[np.isfinite(returns)]
    if len(r) < 2 or r.std(ddof=1) < 1e-12:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR))


def fetch_stablecoin_supply() -> tuple[np.ndarray, np.ndarray]:
    """DefiLlama total stablecoin circulating USD, daily. Returns (day_ts, usd)."""
    with urllib.request.urlopen(DEFILLAMA_STABLES, timeout=30) as resp:
        data = json.loads(resp.read())
    days, usd = [], []
    for row in data:
        ts = int(row["date"])
        cu = row.get("totalCirculatingUSD", {})
        val = cu.get("peggedUSD") if isinstance(cu, dict) else None
        if val is None or val <= 0:
            continue
        days.append((ts // DAY) * DAY)
        usd.append(float(val))
    return np.array(days, dtype=np.int64), np.array(usd, dtype=float)


def load_daily_eth_close(db: str = "historical_data.db") -> dict[int, float]:
    """Resample local 5m candles to daily close keyed by UTC day timestamp."""
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT timestamp, close FROM candles ORDER BY timestamp"
    ).fetchall()
    con.close()
    daily: dict[int, float] = {}
    for ts, close in rows:
        daily[(int(ts) // DAY) * DAY] = float(close)  # last close of the day wins
    return daily


def fetch_binance_daily_close(symbol: str) -> dict[int, float]:
    """Free deep-history daily close via Binance spot klines (paginated, 1000/call).

    No auth, reliable, history since ~2017. Used for out-of-cycle confirmation on
    assets/periods the signal was NOT discovered on (e.g. BTCUSDT, ETH pre-2023).
    """
    daily: dict[int, float] = {}
    start_ms = 1500000000000  # 2017-07
    now_ms = int(time.time() * 1000)
    while start_ms < now_ms:
        url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}"
               f"&interval=1d&startTime={start_ms}&limit=1000")
        with urllib.request.urlopen(url, timeout=30) as resp:
            kl = json.loads(resp.read())
        if not kl:
            break
        for k in kl:
            open_ms, close_px = int(k[0]), float(k[4])
            daily[(open_ms // 1000 // DAY) * DAY] = close_px
        newest = max(int(k[0]) for k in kl)
        if len(kl) < 1000:
            break
        start_ms = newest + DAY * 1000
        time.sleep(0.2)
    return daily


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--growth-win", type=int, default=7,
                    help="lookback (days) for stablecoin supply growth rate")
    ap.add_argument("--zwin", type=int, default=30, help="rolling zscore window")
    ap.add_argument("--cost-bps", type=float, default=10.0,
                    help="round-trip cost per position change, in bps")
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="only take a position when |zscore| exceeds this")
    ap.add_argument("--long-only", action="store_true",
                    help="realistic for a spot wallet: clip short positions to flat (0)")
    ap.add_argument("--signal", choices=["stablecoin", "price-mom"], default="stablecoin",
                    help="'price-mom' is a falsification benchmark: same pipeline driven "
                    "by price momentum instead of supply. Stablecoin must beat it.")
    ap.add_argument("--price-source", choices=["local", "binance"], default="local",
                    help="'binance' fetches deep free daily klines for out-of-cycle tests.")
    ap.add_argument("--asset", choices=["eth", "btc"], default="eth",
                    help="asset to test the (global) stablecoin signal against.")
    ap.add_argument("--from-ym", default="", help="restrict to days >= YYYY-MM (out-of-cycle slicing)")
    ap.add_argument("--to-ym", default="", help="restrict to days <= YYYY-MM")
    args = ap.parse_args()

    print("fetching DefiLlama stablecoin supply (free) ...")
    sdays, susd = fetch_stablecoin_supply()
    print(f"stablecoin points: {len(sdays)}")
    if args.price_source == "binance":
        symbol = {"eth": "ETHUSDT", "btc": "BTCUSDT"}[args.asset]
        print(f"fetching {symbol} daily closes from Binance ...")
        eth = fetch_binance_daily_close(symbol)
        print(f"binance {symbol} daily closes: {len(eth)}")
    else:
        eth = load_daily_eth_close()
        print(f"local ETH daily closes: {len(eth)}")

    # align on the intersection of days that have both supply and price
    s_by_day = dict(zip(sdays.tolist(), susd.tolist()))
    common = sorted(set(s_by_day) & set(eth))

    def ym_to_ts(ym: str) -> int:
        y, m = (int(x) for x in ym.split("-"))
        return int(time.mktime((y, m, 1, 0, 0, 0, 0, 0, 0)))

    if args.from_ym:
        lo = ym_to_ts(args.from_ym)
        common = [d for d in common if d >= lo]
    if args.to_ym:
        hi = ym_to_ts(args.to_ym)
        common = [d for d in common if d <= hi]
    if len(common) < 200:
        print(f"FAIL: only {len(common)} overlapping days — cannot test.")
        return 1
    days = np.array(common, dtype=np.int64)
    supply = np.array([s_by_day[d] for d in common], dtype=float)
    price = np.array([eth[d] for d in common], dtype=float)
    print(f"aligned days: {len(days)}  "
          f"({time.strftime('%Y-%m', time.gmtime(days[0]))} -> "
          f"{time.strftime('%Y-%m', time.gmtime(days[-1]))})")

    # signal = causal zscore of growth in the chosen driver (bullish when rising)
    g = args.growth_win
    driver = price if args.signal == "price-mom" else supply
    growth = np.full(len(driver), np.nan)
    growth[g:] = driver[g:] / driver[:-g] - 1.0
    z = rolling_zscore(growth, args.zwin)
    sig = z
    print(f"signal driver: {args.signal}")

    # forward daily return (next-day holding period)
    fwd = np.full(len(price), np.nan)
    fwd[:-1] = price[1:] / price[:-1] - 1.0

    ic_all, p_all = spearman_ic(sig, fwd)
    print(f"\n=== Information Coefficient (signal vs next-day return) ===")
    print(f"overall IC = {ic_all:+.4f}  (p={p_all:.4f}, n={np.isfinite(sig*fwd).sum()})")

    idx = np.where(np.isfinite(sig) & np.isfinite(fwd))[0]
    folds = np.array_split(idx, args.folds)
    pos_folds = sig_folds = 0
    print("walk-forward folds:")
    for k, fold in enumerate(folds):
        rho, p = spearman_ic(sig[fold], fwd[fold])
        t0 = time.strftime("%Y-%m", time.gmtime(days[fold[0]]))
        t1 = time.strftime("%Y-%m", time.gmtime(days[fold[-1]]))
        pos_folds += rho > 0
        sig_folds += p < 0.05
        print(f"  fold {k} [{t0}->{t1}] n={len(fold):4d}  IC={rho:+.4f} "
              f"p={p:.3f} {'+' if rho>0 else '-'}{' *' if p<0.05 else ''}")
    print(f"positive-IC folds: {pos_folds}/{len(folds)}   "
          f"significant(p<0.05): {sig_folds}/{len(folds)}")

    # cost-aware long/short backtest vs buy-and-hold
    pos = np.zeros(len(sig))
    active = np.isfinite(z) & (np.abs(z) > args.threshold)
    pos[active] = np.sign(sig[active])
    if args.long_only:
        pos = np.clip(pos, 0.0, 1.0)
    cost = args.cost_bps / 1e4
    strat_ret = np.full(len(price), np.nan)
    prev = 0.0
    for i in range(len(price)):
        if not np.isfinite(fwd[i]):
            continue
        strat_ret[i] = pos[i] * fwd[i] - cost * abs(pos[i] - prev)
        prev = pos[i]

    sr = strat_ret[np.isfinite(strat_ret)]
    bh = fwd[np.isfinite(fwd)]
    strat_cum = float(np.prod(1 + sr) - 1)
    bh_cum = float(np.prod(1 + bh) - 1)
    turns = int(np.sum(np.abs(np.diff(np.concatenate([[0.0], pos[np.isfinite(fwd)]]))) > 0))

    # per-fold strategy vs buy-hold consistency (is the edge spread, or one lucky fold?)
    print("\nper-fold strategy vs buy-hold (cumulative):")
    win_folds = 0
    for k, fold in enumerate(folds):
        s = strat_ret[fold]; b = fwd[fold]
        s = s[np.isfinite(s)]; b = b[np.isfinite(b)]
        sc = float(np.prod(1 + s) - 1); bc = float(np.prod(1 + b) - 1)
        win = sc > bc
        win_folds += win
        print(f"  fold {k}: strat={sc*100:+7.1f}%  bh={bc*100:+7.1f}%  {'WIN' if win else 'lose'}")
    print(f"folds strategy beats buy-hold: {win_folds}/{len(folds)}")
    print(f"\n=== Cost-aware backtest ({len(sr)} days, cost={args.cost_bps}bps/turn, "
          f"thr={args.threshold}, growth_win={g}) ===")
    print(f"position changes: {turns}")
    print(f"  STRATEGY  net return = {strat_cum*100:+8.1f}%   Sharpe = {sharpe(sr):+.3f}")
    print(f"  BUY&HOLD      return = {bh_cum*100:+8.1f}%   Sharpe = {sharpe(bh):+.3f}")

    beats = (strat_cum > bh_cum) and (sharpe(sr) > sharpe(bh)) and (pos_folds > len(folds)/2)
    print("\n=== VERDICT ===")
    if beats:
        print("PASS: stablecoin-supply signal beats buy-and-hold net of costs AND has "
              "majority positive OOS IC. Candidate edge — promote to deeper validation.")
    else:
        print("NO EDGE (honest): signal does NOT net-beat buy-and-hold ETH. "
              "Per CLAUDE.md PUSULA #3, log it and move to the next alpha source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
