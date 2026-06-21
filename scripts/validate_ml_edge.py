#!/usr/bin/env python3
"""scripts/validate_ml_edge.py — walk-forward OOS validation of the LightGBM brain.

Trains a FRESH LightGBM per fold on past candles and measures predictive power
on the next (unseen) fold — an honest out-of-sample test that the shipped model
(trained on all data) cannot give. Reports directional accuracy, AUC, and the
Information Coefficient (Spearman corr of prediction vs. next-bar return).

Usage:
    python scripts/validate_ml_edge.py --db historical_data.db --folds 6

Interpretation:
    acc ~ 50%      → naive 0.5 threshold is coin-flip (base rate is low)
    AUC > 0.5      → real ranking skill (markets are near-efficient; >0.6 OOS notable)
    IC > 0, p<0.05 → small but real, persistent edge

A positive AUC/IC means the brain has signal; whether that signal survives
trading costs is a separate question (see the cost-aware backtester).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="historical_data.db")
    ap.add_argument("--folds", type=int, default=6)
    ap.add_argument("--warmup", type=int, default=200)
    ap.add_argument("--rounds", type=int, default=200)
    args = ap.parse_args()

    import lightgbm as lgb
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score

    from scripts.train_models import FEATURE_NAMES, build_feature_matrix, build_labels

    con = sqlite3.connect(args.db)
    df = pd.read_sql_query(
        "SELECT timestamp,open,high,low,close,volume_usdc,trade_count,buy_volume_usdc "
        "FROM candles ORDER BY timestamp",
        con,
    )
    con.close()
    print(f"candles: {len(df)}")

    feat = build_feature_matrix(df)
    X = np.nan_to_num(
        feat[FEATURE_NAMES].to_numpy(dtype=float), nan=0.0, posinf=0.0, neginf=0.0
    )
    y = build_labels(df)
    close = df["close"].to_numpy(float)
    fwd = np.zeros(len(close))
    fwd[:-1] = (close[1:] - close[:-1]) / close[:-1]

    s, e = args.warmup, len(X) - 1
    X, y, fwd = X[s:e], y[s:e], fwd[s:e]
    n = len(X)
    print(f"usable rows: {n} | base rate y=1: {y.mean():.3f}\n")

    params = dict(
        num_leaves=63, learning_rate=0.03, min_child_samples=20,
        feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=5,
        lambda_l1=0.1, lambda_l2=0.1, objective="binary", metric="auc",
        verbose=-1, is_unbalance=True,
    )

    k, seg = args.folds, n // (args.folds + 1)
    print(f"{'fold':>4} {'acc%':>6} {'auc':>6} {'IC':>8} {'IC_p':>7} {'n_test':>8}")
    accs, aucs, ics = [], [], []
    for fold in range(1, k + 1):
        tr, te = slice(0, fold * seg), slice(fold * seg, (fold + 1) * seg)
        model = lgb.train(
            params, lgb.Dataset(X[tr], label=y[tr]),
            num_boost_round=args.rounds, callbacks=[lgb.log_evaluation(-1)],
        )
        p = model.predict(X[te])
        yt, ft = y[te], fwd[te]
        acc = float(np.mean((p > 0.5) == yt))
        auc = roc_auc_score(yt, p) if len(set(yt)) > 1 else float("nan")
        ic, icp = spearmanr(p, ft)
        accs.append(acc)
        aucs.append(auc)
        ics.append(ic)
        print(f"{fold:>4} {acc * 100:>6.2f} {auc:>6.3f} {ic:>8.4f} {icp:>7.3f} {len(yt):>8}")

    print(f"\nOOS mean: acc={np.mean(accs) * 100:.2f}%  "
          f"auc={np.mean(aucs):.3f}  IC={np.mean(ics):.4f}")
    print("baseline: acc=50%, no-skill auc=0.5, no-edge IC=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
