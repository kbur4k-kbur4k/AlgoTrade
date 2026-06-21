# Master Roadmap V4 — 2026 Seviyesi DeFi Quant Botu

Bu dosya V3 roadmap'ini supersede eder (2026-04-10).

V1 platform kurdu. V2 ML altyapısı. V3 temel edge. V4 2026'nın tam gücü.

---

## 1. Neden V4?

### 1.1 Simons Yaklaşımı Artık Tavan Değil

Simons 1988-2000'de şunları yaptı:
- HMM + Kalman + istatistiksel arbitraj
- 100+ zayıf bağımsız sinyal → ensemble
- Kelly sizing
- Rakipler teknik analiz yapıyordu → büyük kenar

**2026'da bu kenar yok.** Herkes bu teknikleri biliyor.

### 1.2 2026'da Gerçek Kenar

Simons'ın **hiç sahip olmadığı** 3 şey:

```
1. Foundation Models (TimesFM, Chronos)
   Milyarlarca zaman serisi üzerinde pretrain edilmiş.
   Zero-shot forecasting — tek satır kod, Simons'ın
   yıllar süren modelinden daha iyi.

2. LLM Reasoning (Claude, GPT-4)
   On-chain transaction pattern'ı anlık yorumlama.
   "Bu whale hareketi ne anlama geliyor?" sorusunu
   milisaniyede yanıtlayan sistem.

3. Causal ML (DoWhy, CausalML)
   Korelasyon değil nedensellik.
   Hangi feature gerçekten price'ı drive ediyor,
   hangisi sadece birlikte hareket ediyor?
   Simons bunu formülle tahmin etti, biz hesaplıyoruz.
```

### 1.3 DeFi'nin Özgün Avantajı

```
Borsa (Simons'ın oynadığı):
  - İşlemler gizli
  - Whale hareketleri gecikmeli görünür
  - Order book kısmen gizli

DeFi (bizim oynadığımız):
  - Her işlem public ve anında görünür
  - Whale cüzdanları takip edilebilir
  - Mempool: henüz onaylanmamış işlemler görünür
  - Funding rates: crowded pozisyon bilgisi
  - Likidite değişimleri anlık
```

Bu veri Simons'a hiç verilmedi. Biz sahipiz.

### 1.4 V4 Tamamlanma Kriterleri

```
✓ Foundation Model (TimesFM/Chronos) ensemble'da aktif
✓ LLM sinyal katmanı canlı, IC > 0.03
✓ Causal feature selection uygulandı, spurious correlation temizlendi
✓ On-chain: funding rate + OFI + whale flow IC-validated
✓ IC → sizing gerçek zamanlı bağlı
✓ RL execution agent eğitilmiş ve deploy edilmiş
✓ Multi-asset (ETH, BTC, SOL) korelasyon-aware
✓ Signal factory otomatik çalışıyor
✓ Tiny live: $250 gerçek sermaye, 4 hafta track record
```

---

## 2. Mevcut Durum (V3 sonu, 2026-04-10)

```
✓ Platform (V1-V2): tüm OS katmanları çalışıyor
✓ Exit parametreleri düzeltildi: SL=1%, TP=1.5%
✓ XGBoost AUC=0.77, LightGBM aktif, ensemble çalışıyor
✓ train_fast.py: 28 saniyede model training
✗ On-chain feature: sıfır
✗ Foundation Model: yok
✗ LLM sinyal: yok
✗ Causal ML: yok
✗ IC → sizing bağlantısı: yok
✗ RL execution: fallback formül
```

---

## 3. Kural Seti

V1-V3 kuralları + yeni eklemeler:

### 3.1 Foundation Model Kuralı
Foundation model (TimesFM/Chronos) hiçbir zaman tek başına
trade kararı vermez. Ensemble'ın bir üyesidir, IC ile ölçülür.

### 3.2 LLM Sinyal Kuralı
LLM çıktısı doğrudan pozisyon açmaz.
LLM → sinyal skoru → IC ölçümü → ensemble ağırlığı.
LLM halüsinasyonu riski: her LLM sinyali structured output
zorunluluğu taşır (float [0,1], açıklama ile birlikte).

### 3.3 Causal Kural
Bir feature causal test geçmeden ensemble'a eklenemez.
Korelasyon tek başına yeterli değil.

### 3.4 IC Zorunluluğu (V3'ten devam)
IC < 0.02 → otomatik retire.
IC 0.02–0.05 → izle, yarım ağırlık.
IC > 0.05 → tam ağırlık.

### 3.5 Sıra Kuralı
Phase sırası zorunlu. Foundation model Phase 15'te gelir —
Phase 14 (on-chain) bitmeden başlamaz. Temel olmadan
süslü model fark yaratmaz.

---

## 4. Phase Bağımlılık Haritası

```
[TAMAMLANDI] Phase 12A — Exit Math Fix
    ↓
Phase 12B — IC Measurement (500+ trade)
    ↓
Phase 13  — Fast ML Training (train_fast.py) ✓ AKTIF
    ↓
Phase 14  — On-Chain Intelligence (funding rate, OFI, whale)
    ↓
Phase 15  — Foundation Model (TimesFM/Chronos)
    ↓
Phase 16  — LLM Signal Layer (Claude API)
    ↓
Phase 17  — Causal ML Feature Selection
    ↓
Phase 18  — IC → Sizing Feedback Loop
    ↓
Phase 19  — Multi-Asset + Correlation Kelly (ETH/BTC/SOL)
    ↓
Phase 20  — RL Execution Engine (gerçek eğitilmiş PPO)
    ↓
Phase 21  — Signal Factory (otomatik alpha araştırması)
    ↓
Phase 22  — Multi-Agent Simulation (rakip bot modelleme)
    ↓
Phase 23  — Tiny Live ($250 gerçek sermaye)
```

Phase 14 ve 15 kısmen paralel ilerleyebilir.
Phase 16 ve 17 kısmen paralel ilerleyebilir.

---

## 5. PHASE 12B — Sinyal IC Ölçümü

### 5.1 Hedef
500+ kapalı trade birikince IC hesapla. XGB + LGBM'in
gerçek predictive power'ı ne?

### 5.2 Kapsam
- Bot çalışmaya devam eder, trade birikir
- Her 50 trade sonrası IC hesapla (rolling)
- IC decay: 1-bar, 3-bar, 6-bar horizon
- IC < 0.02: o model ağırlığı düşer

### 5.3 Çıkış Kapısı
1. `/api/signal_scorecard` non-null IC
2. 500+ kapalı trade belgelenmiş

---

## 6. PHASE 13 — Fast ML Training Pipeline ✓ AKTIF

### 6.1 Durum
`train_fast.py` yazıldı ve çalıştırıldı:
- XGBoost AUC=0.7664 — deployed
- LightGBM AUC=0.7483 — deployed
- 28 saniyede tamamlandı

### 6.2 Bakım Kuralı
Her hafta LearningOS tetikler → `train_fast.py` çalışır →
AUC > 0.52 ise deploy → rapor `/data/training_report.json`

### 6.3 Çıkış Kapısı ✓
XGB + LGBM deployed, ensemble aktif, fallback yok.

---

## 7. PHASE 14 — On-Chain Intelligence

### 7.1 Hedef
Price/volume'ün göremediği, fiyattan **önce** gelen sinyaller.

### 7.2 Neden Bu Phase Kritik

```
Simons avantajı: diğerlerinin göremediği veri
DeFi avantajı:  tüm veri public ama kimse kullanmıyor

Funding rate pozitif → kalabalık long → mean reversion yakın
Whale cüzdan hareketi → büyük hareket habercisi
Exchange net outflow → HODLing artıyor → bullish
Order book imbalance → kısa vadeli yön tahmini
```

### 7.3 Sinyal Kataloğu

#### Sinyal 1: Funding Rate (En Önemli)
```python
# Kaynak: Binance/Bybit public API
# Endpoint: GET /fapi/v1/fundingRate
# Güncelleme: 8 saatte bir
# Feature: funding_rate, funding_rate_zscore_30d
# Mantık: yüksek pozitif funding = crowded long = düşüş riski
# Beklenen IC: 0.04-0.07
```

#### Sinyal 2: Exchange Net Flow
```python
# Kaynak: Glassnode free tier veya on-chain RPC
# Feature: net_flow_24h, net_flow_7d_avg, flow_zscore
# Mantık: büyük exchange inflow = satış baskısı yaklaşıyor
# Beklenen IC: 0.03-0.05
```

#### Sinyal 3: Order Flow Imbalance (OFI)
```python
# Kaynak: Binance spot WebSocket (public)
# Feature: ofi_top5_levels, ofi_normalized, ofi_momentum
# Mantık: bid depth >> ask depth → kısa vadeli yukarı baskı
# Beklenen IC: 0.04-0.08 (en hızlı sinyal)
# Not: mevcut kod placeholder, gerçek implement edilecek
```

#### Sinyal 4: Whale Wallet Monitoring
```python
# Kaynak: Etherscan API (free tier) + on-chain RPC
# Feature: whale_net_flow_6h, whale_accumulation_score
# Top 50 ETH holder hareketi → regime değişimi öncüsü
# Beklenen IC: 0.02-0.04
```

#### Sinyal 5: DEX Liquidity Depth Delta
```python
# Kaynak: Uniswap V3 pool RPC (zaten bağlı)
# Feature: liquidity_depth_ratio, depth_change_1h
# Ani likidite çekilmesi → yüksek slippage riski → bekle
# Beklenen IC: 0.02-0.04
```

### 7.4 Entegrasyon Protokolü

```
Her yeni sinyal için zorunlu sıra:
1. Veri toplama modülü yaz (tick_collector'a ekle)
2. Feature üret (alpha_engine feature vector'üne ekle)
3. 200+ observation sonrası standalone IC ölç
4. IC > 0.02 → ensemble'a ekle
5. IC <= 0.02 → signal_catalog'da "gözlemde" bırak
6. Causal test geç (Phase 17'ye hazır)
```

### 7.5 Dosyalar
```
wallet_manager/data/funding_rates.py    (yeni)
wallet_manager/data/onchain_flows.py    (yeni)
wallet_manager/data/order_book.py       (yeni)
wallet_manager/data/whale_tracker.py    (yeni)
```

### 7.6 KPI'lar
- 2+ on-chain sinyal IC > 0.02 kanıtlanmış
- XGB/LGBM feature vector genişledi
- Freshness policy her sinyal için belgelenmiş

### 7.7 Çıkış Kapısı
1. 2+ sinyal standalone IC > 0.02
2. `docs/phase14_onchain.md` per-sinyal IC tablosu

---

## 8. PHASE 15 — Foundation Model Entegrasyonu

### 8.1 Hedef
Google'ın TimesFM veya Amazon'un Chronos modelini
ensemble'a ekle. Simons'ın hiç sahip olmadığı güç.

### 8.2 Neden Foundation Model

```
Simons: kendi modelini yıllarca eğitti
2026:   Google 1 milyar zaman serisi üzerinde
        pretrain etti → zero-shot kullanabilirsin

Avantajlar:
- Zero-shot: yeni eğitim gerekmez
- Transfer learning: tüm piyasaları "gördü"
- Multi-horizon: 1h, 4h, 24h aynı anda
- Uncertainty estimation: güven aralığı verir
```

### 8.3 Model Seçimi

**Birincil: TimesFM (Google)**
```python
# pip install timesfm
# Apache 2.0 lisans, ticari kullanım serbest
# 200M parametre, 5-minute granularity destekli
# Input: son 512 bar → Output: sonraki N bar forecast

from timesfm import TimesFm
model = TimesFm(
    context_len=512,
    horizon_len=12,  # 1 saatlik tahmin (5dk bars)
    backend="cpu",   # Azure CPU'da çalışır
)
```

**Yedek: Chronos (Amazon)**
```python
# pip install chronos-forecasting
# Apache 2.0 lisans
# T5 mimarisine dayalı language model for time series

from chronos import ChronosPipeline
pipeline = ChronosPipeline.from_pretrained("amazon/chronos-t5-small")
```

### 8.4 Ensemble Entegrasyonu

```python
# alpha_engine.py'a eklenecek
class FoundationModelSignal:
    def predict(self, price_history: np.ndarray) -> float:
        """
        Returns prob_up in [0, 1]
        TimesFM → median forecast > current → 1, else 0
        Uncertainty: wide CI → düşük confidence
        """
        forecast = self.model.forecast(price_history)
        prob_up = (forecast.median > price_history[-1]).mean()
        return float(prob_up)
```

### 8.5 Değerlendirme Kriteri

```
Deploy edilir ancak:
IC_foundation > IC_zscore_baseline (price-only)
AUC_foundation > 0.53 held-out test'te
```

Geçmezse ensemble'a girmez, izlemeye alınır.

### 8.6 KPI'lar
- TimesFM veya Chronos ensemble'da aktif
- IC_foundation > 0.03
- Inference latency < 100ms (CPU'da)
- `docs/phase15_foundation_model.md` IC karşılaştırması

### 8.7 Çıkış Kapısı
1. Foundation model IC baseline'dan yüksek belgelenmiş
2. Startup'ta yükleniyor, fallback yok

---

## 9. PHASE 16 — LLM Signal Layer

### 9.1 Hedef
Claude API ile on-chain anomali yorumlama ve
crypto haber sentiment sinyali.
Simons'ın asla sahip olmadığı: dil anlayan sinyal.

### 9.2 Neden LLM Sinyal

```
Price model: "fiyat düştü" görür
LLM:         "Ethereum core developer major güvenlik
              açığı tweet etti, fiyat düşüyor" yorumlar

Price model: pattern tanır
LLM:         neden'i anlar → daha erken sinyal
```

### 9.3 İki LLM Sinyal Kaynağı

#### Kaynak A: On-Chain Anomaly Interpretation
```python
# Her 5 dakikada bir:
# 1. Büyük on-chain transaction'ları tespit et (>$1M)
# 2. Claude API'ye gönder:

prompt = """
Son 5 dakikada ETH on-chain olaylar:
{on_chain_events}

Bu hareketler kısa vadeli fiyat için bullish mi bearish mi?
Sadece şunu döndür: {{"signal": 0.0-1.0, "reason": "tek cümle"}}
signal: 0.0=güçlü bearish, 0.5=nötr, 1.0=güçlü bullish
"""

# Output: {"signal": 0.73, "reason": "Büyük cüzdan exchange'den çekiyor"}
# Bu signal değeri feature olarak kullanılır
```

#### Kaynak B: Crypto News Sentiment
```python
# Kaynak: CryptoCompare news API (free tier) veya RSS
# Her saat başı son 10 haber → Claude → sentiment score
# Feature: news_sentiment_1h, news_sentiment_momentum

prompt = """
Son 1 saatteki ETH haberleri:
{news_headlines}

ETH fiyatı için sonraki 4 saat: bullish mi bearish mi nötr mü?
{"signal": 0.0-1.0, "confidence": 0.0-1.0, "key_factor": "bir kelime"}
"""
```

### 9.4 Güvenlik ve Maliyet

```
Maliyet kontrolü:
- Claude Haiku kullan (ucuz, hızlı)
- Max 100 API call/gün = ~$0.50/gün
- Cache: aynı input 30 dakika cache'lenir

Halüsinasyon koruması:
- Structured output zorunlu (Pydantic validation)
- signal [0,1] dışındaysa → 0.5 (nötr) kullan
- IC < 0.02 olursa otomatik devre dışı

LLM sinyali tek başına asla trade açmaz.
Ensemble'ın bir üyesi, IC ile ölçülür.
```

### 9.5 KPI'lar
- LLM sinyal günde 100+ observation üretiyor
- IC > 0.02 ilk 200 observation sonrası
- API maliyet < $20/ay
- Halüsinasyon oranı < %1 (validation ile)

### 9.6 Çıkış Kapısı
1. LLM sinyal IC > 0.02 kanıtlanmış
2. Maliyet ve güvenlik kontrolleri aktif
3. `docs/phase16_llm_signal.md` mevcut

---

## 10. PHASE 17 — Causal ML Feature Selection

### 10.1 Hedef
Korelasyon değil nedensellik. Simons bunu tahmin etti,
biz hesaplıyoruz.

### 10.2 Problem

```
Normal ML: "Funding rate yüksekken fiyat düşüyor" → feature ekle
Causal ML: "Funding rate NEDEN fiyatı düşürüyor?"
           "Yoksa her ikisi de başka bir şeyden mi etkileniyor?"

Spurious correlation örneği:
Ice cream sales ve boğulma vakası korelasyonlu (sıcak hava → ikisi de artar)
Ice cream fiyatı boğulmayı tahmin etmez

DeFi'de:
Gas price ve volatilite korelasyonlu ama
gas price volatiliteyi drive etmiyor
ikisi de high-activity dönemde birlikte yükseliyor
```

### 10.3 Implementasyon

```python
# pip install dowhy
from dowhy import CausalModel

# Her feature için causal test:
model = CausalModel(
    data=feature_df,
    treatment="funding_rate",
    outcome="next_bar_return",
    common_causes=["market_volatility", "btc_dominance"]
)

# Causal effect estimate
estimate = model.estimate_effect(
    identified_estimand,
    method_name="backdoor.linear_regression"
)

# p_value > 0.05 → spurious → feature'ı kaldır
# p_value < 0.05 → causal → feature tut
```

### 10.4 Beklenti

```
Mevcut 36 feature → Causal test sonrası ~15-20 feature
Az ama güçlü feature → XGB/LGBM overfitting azalır
IC artar çünkü noise azaldı
```

### 10.5 KPI'lar
- Causal test tüm feature'lara uygulandı
- Spurious feature sayısı belgelendi
- Post-causal XGB AUC >= pre-causal AUC

### 10.6 Çıkış Kapısı
1. Causal feature set belgelenmiş
2. Model retrain edildi causal feature'larla
3. `docs/phase17_causal_ml.md` mevcut

---

## 11. PHASE 18 — IC → Position Sizing Feedback

### 11.1 Hedef
IC'yi pasif raporlamadan aktif sizing'e bağla.

### 11.2 Mekanizma

```python
def ic_kelly_multiplier(ic: float, ir: float) -> float:
    """
    IC < 0.02:        × 0.0  (trade etme)
    IC 0.02 - 0.05:   × 0.5
    IC 0.05 - 0.10:   × 1.0
    IC > 0.10:        × 1.5

    IR bonus:
    IR < 0.5:   × 0.8
    IR 0.5-1.0: × 1.0
    IR > 1.0:   × 1.2
    """

# Her 50 trade sonrası ensemble weights güncelle:
for signal in active_signals:
    weight[signal] = softmax(IC_rolling_50[signal])
```

### 11.3 Çıkış Kapısı
1. IC-adjusted sizing aktif ve loglarda görünür
2. IC=0 sinyal için pozisyon açılmıyor

---

## 12. PHASE 19 — Multi-Asset + Correlation Kelly

### 12.1 Hedef
ETH + BTC + SOL. Portfolio seviyesinde risk.

### 12.2 Correlation-Aware Kelly

```python
# ETH-BTC korelasyonu ~0.85 → sizing azalt
# ETH-SOL korelasyonu ~0.75 → sizing azalt

def portfolio_kelly(base_kelly, corr_matrix):
    max_corr = corr_matrix.max()
    if max_corr > 0.7:
        return base_kelly * (1 - (max_corr - 0.7) * 2)
    return base_kelly
```

### 12.3 Per-Asset IC
Her varlık için ayrı model ve ayrı IC ölçümü.
BTC sinyali ETH modeline girmiyor.

### 12.4 Çıkış Kapısı
1. 3 asset × 100+ paper trade
2. Per-asset IC signal scorecard'da

---

## 13. PHASE 20 — RL Execution Engine

### 13.1 Hedef
Gerçekten eğitilmiş PPO agent. "Random sleep = MEV koruması"
anlayışını bitir.

### 13.2 State / Action / Reward

```python
State = [
    gas_price_percentile_24h,   # 0-1
    time_of_day_sin,            # sinüs encoding
    time_of_day_cos,
    volatility_5m,
    liquidity_depth_ratio,
    mempool_congestion,         # pending tx sayısı
    last_3_slippage_bps,        # execution history
    order_size_pct_of_liquidity
]

Action = Discrete(4)  # [execute_now, wait_1_block,
                      #  wait_3_blocks, split_50_50]

Reward = -slippage_bps - gas_cost_normalized
         + execution_success_bonus
```

### 13.3 Training

```python
# Offline RL — paper execution records'tan öğren
# Batch Constrained Q-learning (BCQ)
# 1000+ execution record → train → deploy

# Online fine-tuning: gerçek paper execution'lardan
# her hafta 50 yeni record → retrain
```

### 13.4 Gerçek MEV Koruması

```
Flashbots Protect RPC entegrasyonu
→ transaction'ları private mempool'a gönder
→ sandwich attack riski sıfır
```

### 13.5 Çıkış Kapısı
1. RL agent baseline'dan düşük slippage gösteriyor
2. Flashbots RPC entegre
3. `docs/phase20_rl_execution.md` mevcut

---

## 14. PHASE 21 — Signal Factory

### 14.1 Hedef
Simons'ın en önemli prensibi: sürekli yeni alpha araştırması.
Hypothesis → test → promote/retire döngüsünü otomatikleştir.

### 14.2 Döngü

```
1. Hypothesis kayıt (operatör veya LearningOS önerir)
2. Otomatik backtest (wf_validator)
3. 200 trade paper IC ölçümü
4. IC > 0.02 → promote → ensemble
5. IC < 0.02 → retire → signal_catalog
6. Ayda bir: tüm aktif sinyallerin IC decay review
```

### 14.3 Otomatik Hypothesis Üretimi (2026 seviyesi)

```python
# LLM → yeni sinyal fikirleri üretir
# "Mevcut feature'larla korelasyonu düşük,
#  DeFi'ye özgü yeni sinyal öner"
# → Claude API prompt → structured output
# → otomatik backtest → IC ölçüm

# Haftada 5 yeni hypothesis
# En iyi 1'i live'a promote edilir
```

### 14.4 Çıkış Kapısı
1. 5+ sinyal katalogda (active + retired)
2. Haftalık otomatik IC review çalışıyor
3. 1+ sinyal evidence ile retire edilmiş
4. LLM hypothesis üretimi aktif

---

## 15. PHASE 22 — Multi-Agent Simulation

### 15.1 Hedef
Rakip botların davranışını modelleyerek
onlardan önce pozisyon al.

### 15.2 Yaklaşım

```
DeFi'deki botlar pattern'lere sahip:
- MEV bot: belirli block pozisyonunu hedefler
- Arbitrage bot: price gap oluşunca tetiklenir
- Liquidation bot: threshold'a yakın pozisyonları izler

Bu pattern'leri öğren → onlar harekete geçmeden önce
pozisyon al veya onlardan korun
```

### 15.3 Implementasyon

```python
# 1. Mempool / block data analizi
#    "Bu transaction hangi bot tipi?"
#    Clustering: MEV / arbitrage / whale / liquidation

# 2. Her bot tipi için basit model
#    "MEV bot pattern görünce slippage artar → bekle"
#    "Liquidation cascade başlarken → exit hızlandır"

# 3. Agent simulation
#    Geçmiş bloklarda bot davranışını replay et
#    → hangi koşulda hangi bot aktif?
#    → buna göre execution strategy ayarla
```

### 15.4 Çıkış Kapısı
1. 3 bot tipi sınıflandırılmış ve modellendi
2. Bot aktivitesi execution kararını etkiliyor
3. `docs/phase22_multi_agent.md` mevcut

---

## 16. PHASE 23 — Tiny Live & İlk Gerçek Sermaye

### 16.1 Tüm Ön Koşullar (hepsi sağlanmalı)

```
✓ avg_win/avg_loss > 1.5           (Phase 12A)
✓ XGB + LGBM deployed, AUC > 0.52  (Phase 13) ✓
✓ 2+ on-chain sinyal IC > 0.02     (Phase 14)
✓ Foundation model IC > baseline   (Phase 15)
✓ LLM sinyal IC > 0.02             (Phase 16)
✓ IC → sizing aktif                (Phase 18)
✓ Shadow live: 50+ karşılaştırma   (süregelen)
✓ Sharpe > 0.8 paper'da 500+ trade
✓ RL execution deploy edilmiş      (Phase 20)
```

### 16.2 Kapsam
- live_max_total_capital_usd = $250
- 4 hafta minimum
- Haftalık paper vs live P&L karşılaştırması
- Max drawdown live capital'ın %3'ünü geçemez

### 16.3 Çıkış Kapısı
1. 4 hafta veri, P&L belgelenmiş
2. Realized Sharpe > 0.5 live period'da
3. `docs/phase23_tiny_live.md` mevcut

---

## 17. Global V4 Scorecard

| Boyut | V3 Hedef | V4 Hedef |
|---|---|---|
| Exit math | avg_win/loss > 1.5 | > 2.0 (RL execution ile) |
| Sinyal sayısı | 5+ | 8-10 bağımsız |
| Foundation Model | Yok | TimesFM/Chronos aktif |
| LLM sinyal | Yok | IC-validated, aktif |
| Causal ML | Yok | Spurious feature temizlendi |
| On-chain | 2+ sinyal | 4+ sinyal |
| IC → sizing | Altyapı | Gerçek zamanlı aktif |
| RL execution | Eğitilmiş agent | + MEV koruması |
| Multi-agent | Yok | 3 bot tipi modellendi |
| Gerçek sermaye | $250 | $250 → kanıtlanmış → scale |

---

## 18. 2026 vs Simons Karşılaştırması

| Yetenek | Simons (peak) | V4 Hedef |
|---|---|---|
| Sinyal sayısı | 100+ | 8-10 (kalite > miktar) |
| Veri kaynağı | Kapalı piyasa | Public on-chain (avantaj) |
| Zaman serisi | Kalman/HMM | Foundation Model (daha güçlü) |
| Dil anlama | Yok | LLM sinyal |
| Nedensellik | Sezgi | Causal ML |
| Execution | Özel | RL + Flashbots |
| Rakip analizi | Yok | Multi-agent sim |
| Veri erişim | Sınırlı | Mempool dahil her şey |

---

## 19. Kalıcı Anti-Patterns

```
✗ Foundation model eklemeden önce on-chain feature'ları atla
✗ LLM çıktısını validation olmadan pozisyona çevir
✗ Causal test geçmemiş feature'ı ensemble'a ekle
✗ IC < 0.02 sinyali "ileride düzelir" diye tut
✗ Yeni model ekle ama mevcut model IC'sini ölçme
✗ Phase sırasını atla: her phase bir öncekinin üzerine inşa eder
✗ Kompleks model + zayıf feature = zaman kaybı
```

---

## 20. Gerçekçi Beklenti

Bu roadmap tamamlandığında:

```
Simons'ın 1990-2000 Medallion'unun üzerinde:
✓ LLM reasoning (o dönemde yoktu)
✓ Foundation models (o dönemde yoktu)
✓ Causal ML (o dönemde yoktu)
✓ Public on-chain veri (o dönemde yoktu)
✓ MEV koruması (DeFi'ye özgü)

Simons'ın hâlâ önünde olduğu yerler:
✗ 35 yıllık track record
✗ 300+ araştırmacı
✗ Milyarlarca dolarlık işlem kapasitesi
✗ Tescilli veri erişimi
```

**Net hedef**: Ölçülebilir edge, matematiksel olarak karlı,
2026'nın araçlarıyla güçlendirilmiş DeFi botu.
Medallion değil — ama onun prensiplerini modern AI ile uygulayan
sistematik bir platform.

---

*Son güncelleme: 2026-04-10*
*Supersedes: MASTER_ROADMAP_V3.md*
*Önceki dosyalar: MASTER_ROADMAP.md, MASTER_ROADMAP_V2.md, MASTER_ROADMAP_V3.md*
