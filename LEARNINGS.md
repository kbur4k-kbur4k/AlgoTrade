# LEARNINGS.md — kanıt günlüğü

> Her tur ÖNCE bunu oku, üstüne bin. Aynı şeyi iki kez deneme. Sadece KANITLA
> doğrulanmış bulgular buraya. (ÖLÇÜ: para kazan + sağlam çalış.)

---

## 2026-06-28 — Robustness durumu: chain + session bug ZATEN çözülmüş

CLAUDE.md "ŞU ANKİ GERÇEK" bölümü bayattı. Doğruladım (paper_trades.db):
- Karar 1-3 (Nis 2026): `WRONG_CHAIN`, chain_id=1, session_id='unknown' → **eski**.
- Karar 4-5 (Haz 2026): `cycle_phase=shadow_cycle`, gerçek session_id, WRONG_CHAIN YOK.
- `wallets.local.json` → `chain_id=8453` (Base mainnet). ✅

Sistem artık shadow_cycle'a ulaşıyor. Kalan "0 trade" sebebi chain DEĞİL:
karar 4-5 `action=HOLD / decision_class=SKIPPED`, sebep `FRACDIFF_NON_STATIONARY`
+ `PAPER_SIGNAL_REJECTED`. Reddedilen sinyal = **ölü LGBM beyni** (Faz 1'de
edge'siz kanıtlandı). Onu trade ettirmeye zorlamak = PUSULA #3 ihlali. Yapmadım.

## 2026-06-28 — Funding-rate sinyali: EDGE YOK (yeni alfa denemesi #1)

Hipotez (wallet_manager/data/funding_rates.py): yüksek pozitif perp funding =
kalabalık long = mean-reversion aşağı; düşük/negatif = squeeze yukarı.
Faz 1'in test etmediği kuadrant: NON-price, pozisyonlama sinyali, uzun (8sa)
horizon (maliyetin yönetilebildiği yer).

Test: `scripts/validate_funding_edge.py` — Binance ETHUSDT funding+markPrice
tam tarih (7214 kayıt, 970 gün, 2023-10→2026-06), causal zscore sinyali,
walk-forward IC + maliyet-dahil long/short backtest vs buy-and-hold.

BULGULAR:
- Overall IC = +0.028, **p=0.13 (anlamlı DEĞİL)**. Walk-forward: 4/6 fold pozitif
  ama **0/6 fold p<0.05**. Sinyal istatistiksel olarak zayıf/gürültülü.
- Maliyet duyarlılığı (net getiri vs buy-hold −10.4%):
  - 5bps/thr0 = +5.7% (tek "PASS" — ama iyimser köşe)
  - **10bps/thr0 = −55.6%** (gerçekçi: Binance perp ~8bps round-trip + slippage)
  - 20bps = −92%. Threshold>0 her zaman daha kötü (whipsaw).
- Turnover yüksek: 2911 periyodun ~%30'unda pozisyon flip → maliyet öldürüyor.

VERDICT: **Funding mean-reversion 8sa horizon'da gerçekçi maliyette buy-and-hold'u
NET yenmiyor.** Tam Faz 1 deseni: minik edge'i maliyet yutuyor. Bu spesifik
formülasyon (zscore mean-reversion) ölü. KAPANIŞ DEĞİL: funding'in daha düşük
turnover'lı carry formülasyonu veya başka varlık denenebilir, ama öncelik düşük.

## 2026-06-28 — On-chain stablecoin-supply: EDGE DEĞİL (out-of-cycle çöktü) ⛔

Hipotez: toplam stablecoin arzı = dry powder; arz büyür→ETH bullish. Günlük horizon.
Test: `scripts/validate_onchain_edge.py`, DefiLlama arzı (free) + fiyat.

İLK değerlendirme "ilk geçen edge" dedi (in-window 2023-26 ETH: long-only +272% vs
+15.7%, plato+per-fold+falsifikasyon geçti). **YANLIŞTI** — hepsi AYNI 2023-26
penceresindeydi; walk-forward fold = aynı rejimin alt-dilimi, gerçek OOS değil.

**Out-of-cycle (farklı dönem+varlık, Binance fiyat) REDDETTİ:**
- ETH 2020-2022 (görülmemiş): strateji +7.2% vs buy-hold **+889.9%** ❌
- BTC 2020-2026: +73.5% vs +737.8% ❌ | BTC 2020-22: −33% vs +138% ❌
- ETH 2023-26 (keşif, sanity): +186% vs +31.7% ✓ (SADECE burada)

NİHAİ: overfit/rejim-özgü, monetize edilemez. 2023-26 ETH choppy'sinde "arz daralınca
nakde geç" şans eseri dipleri kaçtı; mega-boğada (2020-22) felaket.

**METODOLOJİ DERSİ (kalıcı):** Tek 3-yıl penceresinde walk-forward = SAHTE GÜVEN.
Gerçek OOS = FARKLI dönem VE FARKLI varlık. Her aday edge artık bu bara tabi.
Entegrasyondan ÖNCE out-of-cycle teyit = doğru karar (paper'a bağlasaydım kuma inşa).

SIRADAKİ ALFA YOLLARI (öncelik):
1. order-book OFI — tarihsel YOK → canlı kaydet + forward-test (Faz 1 mikroyapı edge'i
   burada olabilir ama maliyet sorusu açık).
2. on-chain exchange net flow — bedava kaynak bulunursa (CryptoCompare/Glassnode ücretli).
3. Çok-varlık cross-sectional (tek varlık zamanlamadan, varlıklar-arası sıralama) — farklı sınıf.
4. Beklentiyi yeniden çerçevele (CLAUDE.md kapı c): edge yoksa portföy/altyapı ürünü.
ÖLÜ: OHLCV+LGBM (Faz 1), funding zscore mean-rev, stablecoin-supply timing.
