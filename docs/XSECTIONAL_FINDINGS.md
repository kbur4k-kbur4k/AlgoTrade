# XSECTIONAL_FINDINGS.md — Cross-sectional momentum

_Tarih: 2026-06-28 · Reproduce: `python scripts/validate_xsectional_edge.py`_

## Verdict: GERÇEK FAKTÖR AMA ÇÜRÜMÜŞ — bugün monetize edilemez

Faz 1 tek-varlık (zaman-serisi) momentumu öldürdü. Cross-sectional momentum farklı,
belgelenen bir kripto faktörü (Liu-Tsyvinski-Wu 2022): her periyot 17-coinlik evreni
trailing-getiriyle sırala, long top-k tut, haftalık rebalans. Göreli sıralama →
stablecoin sinyalini öldüren tek-pencere overfit'ine yapısal olarak daha dayanıklı.

**Adil benchmark = EQUAL-WEIGHT HOLD** (tüm sepeti tut), sadece BTC değil.

### Kanıt (long-only, lb=30, k=5, haftalık, 25bps; en iyi config)

| Dönem | Strateji | EW-hold | Sharpe (st/ew) | fold |
|---|---|---|---|---|
| Tam 2020-10→2025-05 | +3166% | +1431% | 1.32 / 1.15 | 5/6 |
| **ERKEN 2020-22** | +908% | +448% | 1.58 / 1.33 | **6/6** |
| **GEÇ 2023-25** | +145% | +138% | **0.93 / 0.92** | **4/6** |

**Yorum:** Edge tamamen erken (2020-22 alt-season, yüksek dispersiyon) dönemden geliyor.
Güncel rejimde (2023-25) EW-hold'a karşı fazlalık ~0 (Sharpe 0.93 vs 0.92, 2.4 yılda +%7).
Klasik faktör çürümesi. Survivorship bias (evren = 2026'ya kadar yaşayanlar; LUNA/FTT yok)
bu sonucu ÜST-SINIR yapar → gerçek muhtemelen daha kötü.

### Dürüstlük kontrolleri
- **Falsifikasyon (reversal/bottom-k):** +167% vs EW +1431%, 1/6 → momentum yönsel
  olarak doğru (reversal değil), ama bu EW'yi yenmesini sağlamıyor.
- **Config seçimi:** lb=30/k=5 sweep'in en iyisiydi (lb=30/k3, lb60, lb90 hepsi EW'yi
  yenemedi) → en iyiyi seçmek overfit riski; o yüzden out-of-cycle split yapıldı, GEÇ
  dönemde çöktü. Tek güçlü config + tek dönem ≠ edge.

**Sonuç:** cross-sectional momentum bugün canlı için monetize edilebilir edge DEĞİL.

## Yan bulgu STRESS-TEST EDİLDİ → o da çürüdü (dürüst düzeltme)

İlk bakışta EW sepet BTC-hold'u yendi (+1431% vs +930%) → "endeks ürünü" sanıldı.
İki kontrol bunu da çökertti:
- **Rebalans primi ≈ 0:** EW-rebalans vs EW-buy&hold(drift): FULL +1431% vs +1571%
  (rebalans DAHA KÖTÜ), ERKEN +448% vs +426%, GEÇ +138% vs +137%. Rebalans değer katmıyor.
- **EW>BTC sadece 2020-22 alt-season + survivorship:** ERKEN EW +448% vs BTC +61%; ama
  **GEÇ 2023-25 BTC +558% (Sharpe 1.85) >> EW +138% (Sharpe 0.92).** Güncel rejimde
  yalın BTC-hold çeşitlendirilmiş sepeti EZİYOR.

Sonuç: "çeşitlendirilmiş endeks" bile out-of-cycle'da yalın BTC-hold'u yenmiyor.
Hâlâ Faz 1'in çekirdek gerçeği geçerli: **basit buy-and-hold'u (baskın varlık) yenen
hiçbir şey bulunamadı.**

## Konsolide durum (4 alfa sınıfı)

OHLCV-ML (Faz1) · funding mean-rev · on-chain stablecoin-supply · xsec-momentum →
hiçbiri maliyet+out-of-cycle sonrası buy-and-hold'u net yenmiyor. "Endeks" konsolasyonu da
güncel rejimde BTC-hold'a yeniliyor. Bu, körü körüne 5. denemeyi zorlamak yerine
operatörle stratejik çatalı konuşma zamanı (CLAUDE.md: "asla pes etme AMA körü körüne
de zorlama" + kapı-c).
