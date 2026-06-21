# Master Roadmap V3 — Jim Simons Seviyesi DeFi Quant Botu

Bu dosya V2 roadmap'ini supersede eder (2026-04-10).

V1 platform inşa etti. V2 ML altyapısını kurdu. V3 gerçek edge'i üretiyor.

---

## 1. Neden V3?

### 1.1 V2'nin Gerçek Durumu

V2 tamamlandığında sistemin durumu:

- Platform katmanları var (Risk OS, Execution OS, Promotion OS, Learning OS)
- ML modeller fallback modunda çalışıyor (gerçek tahmin yok)
- Exit parametreleri matematiksel olarak yanlış:
  - TRAILING_OFFSET_PCT = 0.5% (çok dar)
  - STOP_LOSS_PCT = 3.0% (çok geniş)
  - Sonuç: avg_win/avg_loss = 0.66 → Kelly negatif → sistem kaybetmek zorunda
- IC = NO_DATA (sinyal kalitesi bilinmiyor)
- Tek sinyal: Z-score + RSI (2005 seviyesi)
- On-chain veri: sıfır
- Transformer/RL: kod var, çalışmıyor

### 1.2 V3 Nedir

V3'ün amacı şu soruyu yanıtlamak:

**Modern AI + DeFi'nin şeffaf on-chain verisi birleşince Jim Simons'ın
1990'larda yapamadığı ne yapabiliriz?**

Simons'ın avantajı başkalarının göremediği pattern'leri istatistikle
bulmaktı. DeFi'de tüm işlemler public. Her cüzdan hareketi, her likidite
değişimi, her funding rate anlık görünür. Bu veri Simons'ın hayatında
olmadı.

### 1.3 V3 Tamamlanma Kriterleri

V3 tamamdır ancak şunlar gerçekleştiğinde:

- Exit parametreleri düzeltilmiş ve avg_win/avg_loss > 1.5
- En az 3 DeFi-özel sinyal IC > 0.03 ile kanıtlanmış
- Transformer modeli Z-score'dan ölçülebilir IC artışı sağlıyor
- IC, gerçek zamanlı olarak position sizing'e bağlanmış
- 3 asset (ETH, BTC, SOL) korelasyon-aware Kelly ile çalışıyor
- RL execution agent gerçek slippage'ı azaltıyor
- Shadow live geçilmiş, tiny live aktif, $250 gerçek sermaye

---

## 2. Kural Seti (V1+V2 kurallarına ek)

### 2.1 Matematik Önce Kuralı

Herhangi bir yeni sinyal veya model eklenmeden önce şu kriter sağlanmalı:

```
avg_win_usd / avg_loss_usd > 1.0
```

Bu sağlanmadığı sürece hiçbir yeni phase başlatılamaz.

### 2.2 IC Zorunluluğu

Hiçbir sinyal "değer katıyor" ilan edilemez:

- IC < 0.02 ise: devre dışı bırak
- IC 0.02–0.05 arası: izle, küçük ağırlık ver
- IC > 0.05 ise: ensemble'a dahil et, position sizing'e bağla

### 2.3 On-Chain Öncelik Kuralı

Her yeni sinyal için önce on-chain veri kaynağı araştırılır.
Price/volume türevi sinyal ancak on-chain alternatif yoksa kabul edilir.

### 2.4 Gerçek ML Kuralı

Model "eğitildi" sayılmaz:

- 200+ labeled sample ile walk-forward validated olmadıkça
- Startup log'unda fallback uyarısı yoksa
- Held-out AUC > 0.52 gösterilmedikçe

### 2.5 IC → Sizing Bağlantısı Kuralı

IC sonuçları sadece raporlama için değil, aktif position sizing için
kullanılır. IC düşük sinyalin Kelly weight'i otomatik düşer.

---

## 3. Platform Mimarisi (V3 eklemeleri)

V1/V2 katmanlarına ek yeni katmanlar:

### 3.1 On-Chain Intelligence Layer (YENİ)

Sorumluluklar:
- Exchange net flow takibi (büyük cüzdan hareketleri)
- Funding rate sinyalleri
- DEX liquidity depth değişimi
- Mempool sinyal (opsiyonel, karmaşık)

Dosyalar:
- `wallet_manager/data/funding_rates.py`
- `wallet_manager/data/onchain_flows.py`
- `wallet_manager/data/order_book.py`

### 3.2 Transformer Signal Engine (YENİ)

Sorumluluklar:
- Price/volume time series üzerinde attention-based tahmin
- Multi-horizon prediction (1h, 4h, 24h)
- Z-score'un yerini alacak modern sinyal

Dosyalar:
- `wallet_manager/strategies/transformer_alpha.py`
- `ml_models/transformer_alpha.pt`

### 3.3 RL Execution Engine (YENİ)

Sorumluluklar:
- Gas timing optimizasyonu
- Slippage minimizasyonu
- Gerçek eğitilmiş RL agent (PPO fallback değil)

Dosyalar:
- `wallet_manager/strategies/rl_execution.py`
- `ml_models/rl_execution_agent.pt`

### 3.4 Signal Factory (YENİ)

Sorumluluklar:
- Sistematik hipotez → backtest → IC ölçümü → promote/retire pipeline
- Her sinyalin metadata'sı: kaynak, IC, IR, decay curve, son review tarihi

Dosyalar:
- `wallet_manager/signal_factory.py`
- `wallet_manager/data/signal_catalog.db`

---

## 4. Phase Bağımlılık Haritası

```
PHASE 12A — Exit Math Fix (BLOCKER — hemen)
    ↓
PHASE 12B — Signal IC Measurement (500+ trade bekle)
    ↓
PHASE 13 — Real ML Training Pipeline
    ↓
PHASE 14 — DeFi On-Chain Intelligence
    ↓
PHASE 15 — Transformer Alpha Engine
    ↓
PHASE 16 — IC → Sizing Feedback Loop
    ↓
PHASE 17 — Multi-Asset + Correlation Kelly
    ↓
PHASE 18 — RL Execution Engine
    ↓
PHASE 19 — Signal Factory (Sürekli Alpha Üretimi)
    ↓
PHASE 20 — Tiny Live & First Real Capital
```

Phase 14 ve 15 paralel ilerleyebilir.
Phase 16 Phase 13 ve 14 ikisi de bitmeden başlayamaz.

---

## 5. PHASE 12A — Exit Matematiği Düzeltmesi

### 5.1 Hedef

Botun matematiksel olarak para kazanabilmesini sağla.

### 5.2 Neden Blocker

Şu anda:
- avg_win = $0.073, avg_loss = $0.110
- win/loss ratio = 0.66 (breakeven için 0.695 gerekli)
- Kelly formülü negatif → sistem kaybetmek zorunda

Bu düzeltilmeden hiçbir ML, IC, on-chain sinyal fark yaratmaz.
Çürük temelin üzerine bina kurulmaz.

### 5.3 Kapsam

```python
# algo_strategy.py
TRAILING_OFFSET_PCT: 0.005 → 0.015   # 0.5% → 1.5%
STOP_LOSS_PCT:       0.03  → 0.01    # 3.0% → 1.0%

# kelly_criterion.py
# trade_count parametresini compute_sized_position'a geçir
# Şu an her zaman 0 geçiyor → adaptive_kelly hep 0.10
```

Hedef davranış:
- Kazananlar 1.5% trailing'e kadar çalışır → avg_win artar
- Kaybedenler 1%'de kesilir → avg_loss azalır
- Beklenti: avg_win/avg_loss > 1.5, profit_factor > 1.2

### 5.4 Dosyalar

- `wallet_manager/strategies/algo_strategy.py`
- `wallet_manager/strategies/kelly_criterion.py`
- `wallet_manager/strategies/execution_logic.py`

### 5.5 KPI'lar

Ölçüm bir sonraki 50 kapalı trade üzerinden yapılır:

- avg_win_usd / avg_loss_usd > 1.0 (minimum)
- profit_factor > 1.0
- Kelly formülü pozitif: (p × b - q) / b > 0

### 5.6 Çıkış Kapısı

50 kapalı trade sonrası:
1. avg_win/avg_loss > 1.0 görülmeli
2. Raporlanmış ve Azure'a deploy edilmeli

### 5.7 Anti-Goals

- Stop-loss'u tamamen kaldırma
- Trade size'ı aniden 10x artırma (risk önce)
- "Bu istatistik küçük sample" diyerek geçme

---

## 6. PHASE 12B — Sinyal IC Ölçümü (V2 Phase 12 devamı)

### 6.1 Hedef

Mevcut sinyallerin gerçek edge'i olup olmadığını IC ile kanıtla veya çürüt.

### 6.2 Kapsam

- 500+ kapalı trade biriktir (bot çalışmaya devam eder)
- IC hesapla: tahmin edilen yön vs gerçekleşen getiri (Spearman)
- IR hesapla: IC / std(IC)
- IC decay curve: 1-bar, 3-bar, 6-bar, 12-bar
- SHAP ile hangi feature'ların IC'ye katkısı var
- IC < 0.02 olan sinyalleri retire et

### 6.3 Kritik Ek

IC sonuçları sadece raporlanmaz — position sizing'e bağlanır (Phase 16).
Bu phase'de altyapısı kurulur.

### 6.4 KPI'lar

- 500+ kapalı trade
- IC hesaplı ve non-null en az 2 sinyal için
- Sinyal scorecard'da "aktif" vs "gözlemde" ayrımı mevcut

### 6.5 Çıkış Kapısı

1. `/api/signal_scorecard` non-null IC döndürüyor
2. `docs/phase12b_signal_ic.md` mevcut

---

## 7. PHASE 13 — Gerçek ML Eğitim Pipeline'ı

### 7.1 Hedef

XGBoost ve LightGBM'i gerçek DeFi feature'larıyla eğit.
Fallback moddan çıkart, gerçek tahmin yap.

### 7.2 Neden Önemli

Şu an XGBoost/LightGBM istatistiksel fallback kullanıyor.
"ML modeli çalışıyor" ama aslında formül çalışıyor.
Bu düzeltilmeden ensemble IC'si anlamsız.

### 7.3 Feature Mühendisliği

Price/volume dışı feature'lar öncelikli:

```
Tier 1 (mutlaka olmalı):
- Z-score (normalized, multi-window: 20, 50, 100)
- RSI (14, 28 periyot)
- Volume ratio (current/rolling avg)
- Price vs VWAP (gerçek VWAP, placeholder değil)
- Bollinger band position
- ATR normalized volatility

Tier 2 (Phase 14'te eklenecek, yer ayrılmış):
- Funding rate (8h rolling)
- Exchange net flow (büyük cüzdan)
- Order book imbalance (top 5 level)
- Gas price percentile (market stress proxy)
```

### 7.4 Label Tasarımı

```
Label = sign(price_t+N - price_t) × magnitude_bucket
N = 12 bar (yaklaşık 1 saat, 5 dakikalık candleler için)
Binary: 1 = yukarı, 0 = aşağı
```

Lookahead bias sıfır tolerans — walk-forward split zorunlu.

### 7.5 Eğitim Protokolü

```
1. paper_trades.db + quant_analytics.db'den feature-label extract
2. Walk-forward: 70% train, 15% validation, 15% test (zaman sırası korunur)
3. XGBoost: early stopping, 500 round max
4. LightGBM: early stopping, dart booster
5. Held-out AUC > 0.52 olmazsa deploy yapılmaz
6. Her Sunday otomatik retrain (LearningOS tetikler)
```

### 7.6 KPI'lar

- Startup'ta fallback uyarısı yok
- XGBoost AUC > 0.52 held-out'ta
- LightGBM AUC > 0.52 held-out'ta
- Tahminler sıfır değil, dağılım var
- `docs/phase13_ml_training.md` mevcut

### 7.7 Çıkış Kapısı

1. Her iki model trained weight'le başlıyor
2. Walk-forward AUC > 0.52 belgelenmiş
3. Otomatik retrain script test edilmiş

---

## 8. PHASE 14 — DeFi On-Chain Intelligence

### 8.1 Hedef

Z-score + RSI'ın göremediği, price'dan önce gelen sinyalleri devreye al.

### 8.2 Neden Önemli

Simons'ın avantajı diğerlerinin erişemediği veriyi kullanmaktı.
DeFi'de tüm bu veri herkese açık ama kimse düzgün kullanmıyor.
Bu bizim Medallion avantajımız.

### 8.3 Sinyal Kataloğu

Her sinyal bağımsız IC ölçümüyle validate edilir, IC < 0.02 ise
ensemble'a eklenmez.

#### Sinyal 1: Funding Rate Mean Reversion
```
Kaynak: Binance/Bybit perpetual funding rates (public API)
Mantık: Pozitif funding = kalabalık long = mean reversion bias
Güncelleme: 8 saatte bir
Feature: funding_rate_8h, funding_rate_zscore
Beklenen IC: 0.03–0.06
```

#### Sinyal 2: Exchange Net Flow
```
Kaynak: Glassnode free tier veya on-chain RPC
Mantık: Büyük exchange inflow = potansiyel satış baskısı
Feature: net_flow_24h_usd, net_flow_zscore
Beklenen IC: 0.02–0.05
```

#### Sinyal 3: DEX Liquidity Depth
```
Kaynak: Uniswap V3 pool RPC çağrısı (zaten var)
Mantık: Ani likidite çekilmesi = volatilite artışı, bekle
Feature: liquidity_depth_ratio, depth_change_1h
Beklenen IC: 0.02–0.04
```

#### Sinyal 4: Order Book Imbalance (OFI)
```
Kaynak: Binance spot order book (public WebSocket)
Mantık: Bid/ask depth asimetrisi kısa vadeli yön tahmini
Feature: ofi_top5, ofi_normalized
Beklenen IC: 0.03–0.07
Not: mevcut kod placeholder, gerçek implement edilecek
```

#### Sinyal 5: Whale Wallet Movement (Opsiyonel)
```
Kaynak: Etherscan API (ücretsiz tier) veya on-chain
Mantık: Top 100 ETH holder hareketi regime değişimi öncüsü
Feature: whale_net_flow_6h, whale_accumulation_score
Beklenen IC: 0.02–0.05
```

### 8.4 Entegrasyon Kuralı

Her sinyal şu sırayı izler:
1. Bağımsız veri toplama (tick_collector'a ekle)
2. Feature üretimi (alpha_engine'e ekle)
3. 200+ observation sonrası standalone IC ölçümü
4. IC > 0.02 ise ensemble'a ekle, yoksa "gözlemde" bırak
5. `signal_catalog.db`'ye kaydet

### 8.5 KPI'lar

- En az 2 on-chain sinyal IC > 0.02 ile validated
- Her sinyal için freshness policy belgelenmiş
- Hiçbir sinyal IC < 0.02 iken ensemble'da değil

### 8.6 Çıkış Kapısı

1. 2+ sinyal standalone IC > 0.02 kanıtlanmış
2. `docs/phase14_onchain_intelligence.md` per-sinyal IC tablosu ile

---

## 9. PHASE 15 — Transformer Alpha Engine

### 9.1 Hedef

Z-score'u ve RSI'ı bir Transformer modeli ile replace et.
Modern AI'ın lineer olmayan pattern'leri yakaladığını IC ile kanıtla.

### 9.2 Neden Önemli

Simons lineer istatistik kullandı — o dönemin en iyisiydi.
Bugün attention-based modeller zaman serisi üzerinde çok daha güçlü.
Bu Simons'ı geçebileceğimiz nokta.

### 9.3 Mimari

```
Input: son 60 bar × N feature (price, volume, on-chain)
Model: 2-layer Transformer Encoder
       - 4 attention head
       - d_model = 64
       - dropout = 0.1
Output: 3-class softmax (yukarı / flat / aşağı)

Training:
- Dataset: paper_trades + historical tick data
- Walk-forward: expanding window, quarterly re-fold
- Loss: CrossEntropy + IC regularization
- Optimizer: AdamW, lr=1e-4, weight decay=1e-5
```

### 9.4 Değerlendirme Kriteri

Transformer yalnızca şu durumda deploy edilir:

```
IC_transformer > IC_zscore_baseline
AUC_transformer > 0.53
Sharpe(transformer signals) > Sharpe(current ensemble)
```

IC artmıyorsa deploy yapılmaz — arşivde kalır, retrain beklenir.

### 9.5 KPI'lar

- Transformer Z-score'dan ölçülebilir IC artışı sağlıyor
- Model boyutu < 10MB (Azure'da çalışabilir)
- Inference latency < 50ms
- `docs/phase15_transformer_alpha.md` IC karşılaştırması ile

### 9.6 Çıkış Kapısı

1. IC_transformer > IC_mevcut_ensemble belgelenmiş
2. Walk-forward AUC > 0.53
3. Ensemble'a entegre, startup'ta yükleniyor

---

## 10. PHASE 16 — IC → Position Sizing Feedback Loop

### 10.1 Hedef

IC'yi pasif raporlamadan aktif karar mekanizmasına çevir.
Yüksek IC sinyal → daha büyük pozisyon. Düşük IC → küçük pozisyon.

### 10.2 Neden Önemli

Şu an IC mükemmel hesaplanıyor ama trading logic onu kullanmıyor.
Bu Simons'ın en temel prensibi: ölçülen edge'e göre siz.
Bağlantı olmadan IC sadece güzel bir rapor.

### 10.3 Mekanizma

```python
# Yeni: IC-adjusted Kelly
def ic_adjusted_kelly(base_kelly, signal_ic, ir_score):
    """
    IC < 0.02:  kelly × 0.1  (neredeyse sıfır)
    IC 0.02-0.05: kelly × 0.5
    IC 0.05-0.10: kelly × 1.0
    IC > 0.10:  kelly × 1.5 (yüksek edge, daha büyük bahis)

    IR multiplier (IC tutarlılığı):
    IR < 0.5: × 0.7
    IR > 1.0: × 1.2
    """
    ic_mult = ic_to_kelly_multiplier(signal_ic)
    ir_mult = ir_to_kelly_multiplier(ir_score)
    return base_kelly * ic_mult * ir_mult
```

### 10.4 Sinyal Bazlı Ağırlıklandırma

Her sinyalin IC'sine göre ensemble weight otomatik güncellenir:

```
Her 50 trade sonrası:
  for signal in active_signals:
    weight[signal] = softmax(IC_rolling_50[signal])
  ensemble_prediction = weighted_sum(signal_predictions, weights)
```

### 10.5 KPI'lar

- IC ve position size arasında pozitif korelasyon görülüyor
- IC < 0.02 sinyal için pozisyon görünür şekilde küçülüyor
- Trade journal'da her kararın IC-multiplier'ı kayıtlı

### 10.6 Çıkış Kapısı

1. IC-adjusted position sizing aktif ve loglarda görünür
2. Yüksek IC sinyalde avg trade size > düşük IC sinyalde
3. `docs/phase16_ic_sizing.md` mevcut

---

## 11. PHASE 17 — Multi-Asset + Korelasyon-Aware Kelly

### 11.1 Hedef

ETH tek varlıktan çıkart. BTC ve SOL ekle.
Portfolio seviyesinde korelasyon-aware Kelly uygula.

### 11.2 Neden Önemli

Simons 100+ instrument üzerinde çalışıyordu.
Tek ETH = tüm risk tek faktörde. Diversifikasyon IC'yi stabilize eder.
BTC ve SOL ETH ile korelasyon 0.7–0.9 → sizing buna göre azalmalı.

### 11.3 Korelasyon-Aware Sizing

```python
def portfolio_kelly(asset_kelly, correlation_matrix, exposures):
    """
    Tek asset max exposure = 50% portfolio risk
    Yüksek korelasyon (>0.7) durumunda her varlık sizing azalır:
    adjusted_size = base_size × (1 - max(correlations > 0.7))
    """
```

### 11.4 KPI'lar

- 3 asset eşzamanlı paper modda çalışıyor
- Korelasyon matrisi her cycle güncelleniyor
- ETH-BTC korelasyonu > 0.7 olduğunda sizing görünür azalıyor
- Her varlık için bağımsız IC ölçümü

### 11.5 Çıkış Kapısı

1. 3 varlık her biri 100+ paper trade
2. Per-asset IC signal scorecard'da görünür
3. Korelasyon-aware sizing aktif
4. `docs/phase17_multi_asset.md` mevcut

---

## 12. PHASE 18 — RL Execution Engine

### 12.1 Hedef

Execution zamanlamasını ve gas yönetimini gerçek eğitilmiş bir RL
agent ile optimize et. Mevcut "random sleep = MEV koruması" anlayışını bitir.

### 12.2 Mimari

```
State: [gas_price_percentile, time_of_day, volatility_regime,
        pending_mempool_size, last_slippage_bps, order_size_pct]
Action: [execute_now, wait_1_block, wait_3_blocks, split_order]
Reward: -slippage_bps - gas_cost_normalized + execution_completeness

Training: Paper execution records → offline RL (BCQ veya CQL)
```

### 12.3 Gerçek MEV Koruması

Rastgele sleep yerine:
- Private RPC entegrasyonu (Flashbots Protect veya BloxRoute)
- Commit-reveal scheme paper modda simüle
- Slippage gerçek liquidity depth'e göre hesaplanıyor

### 12.4 KPI'lar

- Avg slippage bps azalıyor (baseline vs RL agent)
- Gas cost percentile düşüyor (kötü timing azalıyor)
- Execution OS TCA records RL kararlarını içeriyor

### 12.5 Çıkış Kapısı

1. RL agent 1000+ execution record üzerinde eğitilmiş
2. RL agent baseline'dan ölçülebilir slippage iyileşmesi gösteriyor
3. `docs/phase18_rl_execution.md` mevcut

---

## 13. PHASE 19 — Signal Factory (Sürekli Alpha Üretimi)

### 13.1 Hedef

Simons'ın en önemli özelliği: sürekli yeni alpha araştırması.
Sinyaller keşfedilir, test edilir, ya promote edilir ya retire edilir.
Bu döngüyü otomatikleştir.

### 13.2 Kapsam

```
Signal Factory Pipeline:
1. Hypothesis kayıt (operatör veya LearningOS önerir)
2. Otomatik backtest (wf_validator)
3. Paper mode IC ölçümü (200 trade minimum)
4. IC > 0.02: promote → ensemble'a ekle
5. IC < 0.02: retire → signal_catalog'da "retired" olarak kaydet
6. Her ayın 1'i: tüm aktif sinyallerin IC decay review'u

Otomasyon:
- LearningOS haftalık signal health check tetikler
- IC decay > %30 olan sinyal otomatik "review" moduna alınır
- Review modunda position weight yarıya düşer
```

### 13.3 Signal Catalog Şeması

```sql
CREATE TABLE signal_catalog (
    signal_id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    source_type TEXT,  -- 'price', 'onchain', 'sentiment', 'alternative'
    status TEXT,       -- 'active', 'review', 'retired', 'candidate'
    ic_30d REAL,
    ic_90d REAL,
    ir_score REAL,
    decay_rate REAL,
    created_at REAL,
    last_review_at REAL,
    retirement_reason TEXT
);
```

### 13.4 KPI'lar

- En az 5 sinyal signal_catalog'da (active + retired dahil)
- Haftalık otomatik IC review çalışıyor
- En az 1 sinyal evidence ile retire edilmiş

### 13.5 Çıkış Kapısı

1. Signal Factory pipeline uçtan uca çalışıyor
2. 5+ sinyal catalog'da
3. `docs/phase19_signal_factory.md` mevcut

---

## 14. PHASE 20 — Tiny Live & İlk Gerçek Sermaye

### 14.1 Hedef

Evidence ile desteklenen, kontrollü ilk gerçek sermaye deployment'ı.

### 14.2 Ön Koşullar (Hepsi sağlanmalı)

```
✓ avg_win/avg_loss > 1.5 (Phase 12A)
✓ IC > 0.03 en az 2 sinyal için (Phase 14)
✓ Shadow live: ≥50 karşılaştırma, deviation < 0.1% (Phase 13 devamı)
✓ PromotionOS: ≥1 deney SHADOW aşamasında (Phase 13)
✓ 3 asset paper mode'da (Phase 17)
✓ LearningOS: ≥4 tamamlanmış cycle
✓ Sharpe > 0.8 paper modda 500+ trade üzerinden
```

Tek bir ön koşul eksikse tiny live başlamaz.

### 14.3 Kapsam

- live_max_total_capital_usd = $250
- 4 hafta boyunca izle
- Her hafta: paper vs live P&L karşılaştırması
- Sapma > %20 ise otomatik pause

### 14.4 KPI'lar

- 4 hafta boyunca kill-switch tetiklenmiyor
- Realized Sharpe > 0.5 live period'da
- Slippage sapması paper'dan < %20
- Max drawdown live capital'ın %3'ünü geçmiyor

### 14.5 Çıkış Kapısı

1. 4 haftalık live data mevcut, P&L belgelenmiş
2. PromotionOS SHADOW → TINY_LIVE geçişi auditable
3. `docs/phase20_tiny_live.md` mevcut

---

## 15. Global V3 Scorecard

| Boyut | V2 Çıkış | V3 Hedef |
|---|---|---|
| Exit math | avg_win/avg_loss = 0.66 | > 1.5 |
| Kelly sign | Negatif | Pozitif |
| Sinyal sayısı | 1 (Z-score + RSI) | 5+ (on-chain dahil) |
| IC | NO_DATA | > 0.03, 2+ sinyal için |
| IC → Sizing | Bağlantısız | Aktif feedback loop |
| Transformer | Stub | Deployed, IC > baseline |
| RL Execution | Formül fallback | Eğitilmiş agent |
| Asset sayısı | 1 (ETH) | 3 (ETH, BTC, SOL) |
| On-chain sinyal | 0 | 2+ IC-validated |
| Gerçek sermaye | $0 | $250, 4 hafta track record |

---

## 16. Kalıcı Anti-Patterns

Bunlar asla yapılmaz:

- IC ölçülmeden yeni sinyal ensemble'a ekleme
- Matematiksel olarak kaybeden parametrelerle (win/loss < 1.0) çalışmaya devam
- Shadow live geçmeden tiny live açma
- "Bu istatistik küçük sample" diyerek negatif Kelly ile devam
- ML stub'ı "çalışıyor" ilan etme (fallback log yoksa gerçek değil)
- Phase sırasını atlama: her phase bir öncekinin üzerine inşa eder
- On-chain sinyal IC'si < 0.02 iken ensemble'da tutma
- Sürekli yeni phase eklemek yerine mevcut phase'leri düzgün kapatma

---

## 17. Gerçekçi Beklenti

Bu roadmap tamamlandığında elde edilecek:

```
✓ Gerçek edge: IC ile kanıtlanmış, matematiksel olarak karlı
✓ Modern AI: Simons'ın sahip olmadığı Transformer + RL execution
✓ DeFi avantajı: On-chain veri kimsenin tam kullanamadığı
✓ Sistematik research: Sinyaller evidence ile promote/retire
✓ Kontrollü büyüme: Paper → Shadow → Tiny Live → Scale
```

Bu, Medallion Fund değil. Ama:
- Matematiksel olarak karlı
- Ölçülebilir edge
- Modern AI ile güçlendirilmiş
- DeFi'ye özgü avantajlarla donanmış

**Simons'ın prensibini uyguluyor: measure → research → promote →
scale. Hype değil, evidence.**

---

*Son güncelleme: 2026-04-10*
*Önceki: MASTER_ROADMAP_V2.md (Phase 12-16 bu dosyayla replace edilmiştir)*
