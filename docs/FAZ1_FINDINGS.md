# Faz 1 — Doğrulama Bulguları (Edge Var Mı?)

Tarih: 2026-06-21. Veri: `historical_data.db`, 315.361 adet 5-dk ETH mumu (~3 yıl, Binance).

Tüm sonuçlar **maliyet-dahil** (slippage + gas) ve mümkün olduğunda **out-of-sample (walk-forward)**.

## 1. Maliyet-dahil backtest motoru çalışıyor
`EventDrivenBacktester` (slippage_bps + gas_usd_per_trade) 3 yıllık veride çalıştırıldı.
Çıktı: net PnL, getiri, Sharpe, max drawdown, maliyet kırılımı.

## 2. Naive momentum stratejisi: OOS edge YOK

Basit log-momentum (alpha_threshold üstü → long), 10bps slippage + $0.10 gas:

| alpha_threshold | trade | net getiri | Sharpe |
|---|---|---|---|
| 0.025 | 91 | **−7.5%** | 0.045 |
| 0.05 (in-sample seçim) | 10 | +20.3% | 0.40 |

Walk-forward (eşiği train'de seç, OOS test'te ölç), 7 fold:
- Train Sharpe'ları 2.0–3.0 ama **OOS Sharpe ortalaması 0.068**, pozitif fold 3/7.
- In-sample "+%20" **overfitting**'di; walk-forward yakaladı.
- **Verdict: naive momentum'un OOS edge'i yok.**

## 3. LightGBM "beyni": KÜÇÜK AMA GERÇEK OOS edge VAR

Taze lgbm her fold'da geçmişte eğitilip görmediği fold'da test edildi (6 fold, ~2.5 yıl OOS).
Hedef: sonraki bar > %0.1 yükseliş (base rate %20.7).

| Metrik | OOS ortalama | Baseline | Yorum |
|---|---|---|---|
| Directional accuracy | 50.3% | 50% | 0.5 eşiği kalibresiz (base rate düşük) |
| **AUC** | **0.643** | 0.5 | tüm fold'larda 0.62–0.67 → **gerçek sıralama gücü** |
| **IC** (Spearman, pred↔ileri getiri) | **+0.013** | 0 | küçük ama 5/6 fold'da p<0.05 → **anlamlı, kalıcı** |

**Verdict: ML beyninin küçük ama gerçek, kalıcı bir OOS edge'i var** (momentum'un aksine).
AUC 0.64 finansal tahminde kayda değer; piyasalar verimliye yakındır.

## 4. Açık olan kritik soru
Edge KÜÇÜK (IC 0.013). Asıl mesele: bu sinyal **işlem maliyetini aşacak kadar büyük mü?**
Momentum tam burada öldü. Küçük edge ancak **seçici, maliyet-farkında execution**'la
hasat edilir → **Trade Quality Gate**'in varlık sebebi.

**Sıradaki deney:** lgbm sinyalini Trade Quality Gate ile (yalnız yüksek-conviction,
net-edge > maliyet) OOS + maliyetle trade et → net pozitif mi? Bu, "para kazanılabilir mi"
sorusunun nihai cevabı.

## Tekrar üretmek için
```bash
python scripts/validate_ml_edge.py --db historical_data.db --folds 6      # ML OOS edge
python scripts/backtest.py --event-driven --db-path historical_data.db \
    --slippage-bps 10 --gas-usd 0.10 --alpha-threshold 0.05               # momentum baseline
```
