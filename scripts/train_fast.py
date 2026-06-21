"""
train_fast.py — Phase 13 hızlı training (V3)

Hedef: 5 dakikada XGBoost + LightGBM deploy.
- 20K sample (son N candle, zaman sırası korunur)
- 80/20 temporal split (CPCV yok)
- AUC > 0.52 → deploy
- AUC <= 0.52 → log, deploy yok
"""

from __future__ import annotations
import asyncio, json, logging, os, sys, time
from pathlib import Path
import numpy as np

log = logging.getLogger("train_fast")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-8s | %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])

MODELS_DIR  = Path(os.environ.get("MODELS_DIR", "/app/ml_models"))
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "/app/data/training_report.json"))
SAMPLE_SIZE = 20_000   # son N candle
MIN_AUC     = 0.52
SPLIT       = 0.80     # 80% train, 20% test


async def load_data():
    sys.path.insert(0, "/app")
    from scripts.data.historical_data_pipeline import HistoricalDataPipeline
    p = HistoricalDataPipeline()
    df = await p.load_for_training()
    log.info("Loaded %d candles total", len(df))
    # son SAMPLE_SIZE candle al
    df = df.tail(SAMPLE_SIZE).reset_index(drop=True)
    log.info("Using last %d candles", len(df))
    return df


def build_features(df) -> tuple[np.ndarray, np.ndarray]:
    """Basit 8 feature — hızlı, güvenilir."""
    c  = df["close"].values.astype(float)
    v  = df["volume_usdc"].values.astype(float)
    bv = df.get("buy_volume_usdc", df["volume_usdc"] / 2).values.astype(float)
    sv = v - bv

    def sma(x, n): return np.convolve(x, np.ones(n)/n, mode="same")
    def std(x, n):
        out = np.zeros(len(x))
        for i in range(n, len(x)):
            out[i] = x[i-n:i].std()
        return out

    sma20 = sma(c, 20)
    sma50 = sma(c, 50)
    s20   = std(c, 20)

    zscore = np.where(s20 > 0, (c - sma20) / s20, 0.0)

    # RSI(14)
    delta = np.diff(c, prepend=c[0])
    gain  = np.maximum(delta, 0)
    loss  = np.maximum(-delta, 0)
    ag = np.convolve(gain, np.ones(14)/14, mode="same")
    al = np.convolve(loss, np.ones(14)/14, mode="same")
    rsi = np.where(al > 0, 100 - 100/(1 + ag/np.maximum(al, 1e-8)), 50.0)

    # OFI
    tv  = np.maximum(bv + sv, 1e-8)
    ofi = (bv - sv) / tv

    # Volume ratio
    vol_ratio = v / (sma(v, 20) + 1e-8)

    # Price momentum
    mom = np.roll(c, -5) / np.maximum(c, 1e-8) - 1.0
    mom[-5:] = 0.0

    # SMA crossover
    cross = sma20 - sma50

    X = np.column_stack([zscore, rsi, ofi, vol_ratio, mom, cross, np.log(np.maximum(v, 1)), s20 / (c + 1e-8)])

    # Label: 1 jika next-bar fiyat > şu an × 1.001
    label = (np.roll(c, -1) > c * 1.001).astype(int)
    label[-1] = 0

    # NaN/inf temizle
    X = np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=-1.0)

    return X, label


def train_xgb(X_tr, y_tr, X_te, y_te) -> dict:
    try:
        import xgboost as xgb
        from sklearn.metrics import roc_auc_score
    except ImportError:
        return {"error": "xgboost not installed"}

    neg, pos = (y_tr == 0).sum(), (y_tr == 1).sum()
    spw = neg / max(pos, 1)
    log.info("XGBoost train=%d test=%d scale_pos_weight=%.2f", len(y_tr), len(y_te), spw)

    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=spw, eval_metric="logloss",
        tree_method="hist", verbosity=0, random_state=42,
        early_stopping_rounds=20,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

    proba = model.predict_proba(X_te)[:, 1]
    auc   = roc_auc_score(y_te, proba)
    log.info("XGBoost AUC: %.4f", auc)

    result = {"auc": round(auc, 4), "deployed": False}
    if auc >= MIN_AUC:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = MODELS_DIR / "xgb_alpha_model.json"
        model.save_model(str(path))
        log.info("XGBoost DEPLOYED → %s", path)
        result["deployed"] = True
    else:
        log.warning("XGBoost AUC %.4f < %.4f — not deployed", auc, MIN_AUC)
    return result


def train_lgbm(X_tr, y_tr, X_te, y_te) -> dict:
    try:
        import lightgbm as lgb
        from sklearn.metrics import roc_auc_score
    except ImportError:
        return {"error": "lightgbm not installed"}

    neg, pos = (y_tr == 0).sum(), (y_tr == 1).sum()
    log.info("LightGBM train=%d test=%d", len(y_tr), len(y_te))

    model = lgb.LGBMClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        scale_pos_weight=neg/max(pos, 1),
        random_state=42, verbose=-1,
    )
    model.fit(X_tr, y_tr,
              eval_set=[(X_te, y_te)],
              callbacks=[lgb.early_stopping(20, verbose=False), lgb.log_evaluation(-1)])

    proba = model.predict_proba(X_te)[:, 1]
    auc   = roc_auc_score(y_te, proba)
    log.info("LightGBM AUC: %.4f", auc)

    result = {"auc": round(auc, 4), "deployed": False}
    if auc >= MIN_AUC:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        path = MODELS_DIR / "lgbm_alpha_model.txt"
        model.booster_.save_model(str(path))
        log.info("LightGBM DEPLOYED → %s", path)
        result["deployed"] = True
    else:
        log.warning("LightGBM AUC %.4f < %.4f — not deployed", auc, MIN_AUC)
    return result


async def main():
    t0 = time.time()
    log.info("=== train_fast.py — Phase 13 Hızlı Training ===")

    df = await load_data()
    X, y = build_features(df)
    log.info("Features: %s | Label balance: %.3f", X.shape, y.mean())

    split = int(len(X) * SPLIT)
    X_tr, y_tr = X[:split], y[:split]
    X_te, y_te = X[split:], y[split:]

    xgb_res  = train_xgb(X_tr, y_tr, X_te, y_te)
    lgbm_res = train_lgbm(X_tr, y_tr, X_te, y_te)

    report = {
        "timestamp": time.time(),
        "sample_size": len(X),
        "split": SPLIT,
        "xgb":  xgb_res,
        "lgbm": lgbm_res,
        "elapsed_sec": round(time.time() - t0, 1),
        "any_deployed": xgb_res.get("deployed") or lgbm_res.get("deployed"),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    log.info("=== Done in %.1fs ===", report["elapsed_sec"])
    log.info("XGB AUC=%.4f deployed=%s | LGBM AUC=%.4f deployed=%s",
             xgb_res.get("auc", 0), xgb_res.get("deployed"),
             lgbm_res.get("auc", 0), lgbm_res.get("deployed"))

    if not report["any_deployed"]:
        log.warning("Hiç model deploy edilmedi. AUC < %.2f. Data veya feature problemi olabilir.", MIN_AUC)


if __name__ == "__main__":
    asyncio.run(main())
