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

## 5. NİHAİ DENEY: sinyal maliyeti aşıyor mu? + buy-and-hold kıyası

lgbm OOS tahminleri (270k bar, 2.57 yıl) maliyetle trade edildi.

**Native 5-dk frekansı:** brüt pozitif ama NET her eşikte felaket negatif
(−262%…−4665%) — binlerce işlem küçük edge'i (IC 0.013) yok ediyor.

**Düşük frekans (1-gün hold) + yüksek seçicilik (pred>0.8):** net +81%, Sharpe ~0.64,
738 işlem. Seçilen barlar ortalamanın **4×**'i (0.13bp vs 0.03bp/bar) → gerçek seçim becerisi.

**AMA buy-and-hold kıyası belirleyici:**
- Buy-and-hold ETH (OOS): **+87.9%, Sharpe 0.514**
- En iyi strateji: +81% (< +88%), Sharpe 0.64 (> 0.51 ama %60 piyasa-dışı kaldığı için).

## NİHAİ VERDICT (Faz 1 karar kapısı)

- **ML'in gerçek ama küçük seçim becerisi var** (AUC 0.64, IC 0.013, seçili bar 4× getiri).
- **Ancak maliyet sonrası buy-and-hold ETH'i konvansiyonel olarak YENMİYOR.** Marjinal
  risk-ayarlı iyileşme, gerçek sürtünmeler (küçük-hesap gas, gerçek slippage, MEV,
  5-dk execution) altında büyük olasılıkla kaybolur.
- **"Para kazanılabilir mi?" → gerçekçi olarak hayır** — en azından sadece ETH tutmayı
  geçecek, maliyet-sonrası net bir biçimde değil.

## 6. Uzun-horizon edge denemesi (umut yolu #1) — BAŞARISIZ

lgbm 4-saat ve 1-gün getiri etiketiyle yeniden eğitildi (walk-forward OOS):

| Horizon | OOS AUC | IC | Buy&hold'u yenen? |
|---|---|---|---|
| 5-dk | 0.643 | +0.013 | hayır (maliyet öldürüyor) |
| 4-saat | 0.516 | +0.023 | hayır (tüm eşikler net negatif) |
| 1-gün | 0.500 | −0.013 | hayır (edge sıfır) |

**Edge kısa-horizon (5-dk) mikroyapı edge'idir; uzun horizon'da kaybolur** (AUC 0.64→0.50).
Edge'in olduğu yerde maliyet öldürüyor; maliyetin yönetilebildiği yerde edge yok.
**Monetize edilebilir bir horizon yok.**

## KESİN KAPANIŞ

Edge ile maliyet-uygunluğun bir arada olduğu hiçbir frekans bulunamadı. Bu strateji
sınıfı (mevcut feature seti + lgbm) küçük sermaye + on-chain maliyetle para kazandırmaz.

### Kalan gerçekçi yollar
1. **Beklentiyi yeniden çerçevele:** portföy/öğrenme projesi veya altyapı-ürünü (backtest
   framework, C yolu). Mühendislik gerçek; ama "fon" değil.
2. **Farklı veri/feature sınıfı:** mevcut OHLCV-türevi feature'lar tükendi. Gerçek edge
   için farklı alfa kaynağı (on-chain akış, alternatif veri) gerekir — yeni araştırma.
3. **Gerçek parayı tut:** paper modda kal. Kanıt yok.

## Tekrar üretmek için
```bash
python scripts/validate_ml_edge.py --db historical_data.db --folds 6      # ML OOS edge
python scripts/backtest.py --event-driven --db-path historical_data.db \
    --slippage-bps 10 --gas-usd 0.10 --alpha-threshold 0.05               # momentum baseline
```
