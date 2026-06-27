# ONCHAIN_FINDINGS.md — Stablecoin-supply alfa

_Tarih: 2026-06-28 · Reproduce: `python -m scripts.validate_onchain_edge`_

## ⛔ NİHAİ VERDICT: EDGE DEĞİL (out-of-cycle'da çöküyor)

İlk değerlendirme "ilk geçen edge" dedi — **YANLIŞTI.** Tüm o kanıtlar (parametre
platosu, per-fold, fiyat-momentum falsifikasyonu) **aynı 2023-2026 ETH penceresi
içindeydi**; walk-forward fold'lar aynı rejimin alt-dilimleri = gerçek OOS değil.
Gerçek out-of-cycle test (farklı dönem + farklı varlık) sinyali **reddediyor**:

| Test (gw7/zw30/20bps/long-only) | Strateji | Buy-hold |
|---|---|---|
| ETH 2023-2026 (KEŞİF dönemi) | +186%…+272% | +16…32% |
| ETH **2020-2022** (görülmemiş) | **+7.2%** | **+889.9%** |
| BTC 2020-2026 (farklı varlık) | +73.5% | +737.8% |
| BTC 2020-2022 | −33% | +138% |

Sadece keşfedildiği pencerede çalışıyor → **overfit / rejim-özgü, monetize edilemez.**
2023-26 ETH choppy+drawdown'lu; "arz daralınca nakde geç" o dönemin diplerinden
şans eseri kaçtı. 2020-22 mega-boğada nakitte oturmak +890%'ı kaçırdı.

**METODOLOJİ DERSİ (kritik):** Tek 3-yıllık pencerede walk-forward = sahte güven.
Gerçek OOS = FARKLI dönem VE FARKLI varlık. Bundan sonra her aday edge bu bara tabi.
(Faz 1'in NEGATİF sonucu güvende — o da 3yr ama "edge yok" dedi.)

Aşağıdaki orijinal in-window analiz tarihsel kayıt için bırakıldı; verdict yukarıdadır.

---

## Özet (orijinal — in-window, yanıltıcıydı)

Faz 1, "farklı alfa kaynağı (on-chain akış / alt-veri)" kapısını açık bırakmıştı.
Hedeflenen CEX exchange-balance flow ücretli key gerektiriyor (CryptoCompare 401),
o yüzden aynı tezin **bedava, derin-tarihli** vekili test edildi: **toplam stablecoin
arzı = kriptonun "dry powder"ı.**

**Hipotez:** stablecoin arzı büyüyor → kriptoya yeni alım gücü giriyor → ETH bullish;
arz daralıyor → sermaye çıkıyor → bearish. NON-price sinyal, günlük (uzun) horizon —
Faz 1'in fiyat-edge'inin kaybolduğu ama maliyetin yönetilebildiği kuadrant.

**VERDICT: İLK MONETİZE-EDİLEBİLİR-ADAY EDGE.** OOS + maliyet-dahil barını geçen ilk sinyal.
(Hâlâ paper; canlı için out-of-cycle teyit + operatör onayı gerekir — DEĞİŞMEZ KURAL.)

## Veri (ikisi de bedava, key yok)

- Stablecoin toplam arzı (USD): DefiLlama `stablecoincharts/all` — günlük, 2017'den.
- ETH fiyatı: yerel `historical_data.db` candle'ları günlük close'a resample (dış bağımlılık yok).
- Hizalanan: 1096 gün (2023-04 → 2026-04), bir tam piyasa döngüsü.

## Sinyal

`signal = causal_zscore( supply[t]/supply[t-g] - 1 )` ; pozitif z → ETH long.
Causal (geçmiş-only) → IC doğası gereği OOS. Long-only varyant spot DEX wallet'a uygun
(short altyapısı gerekmez).

## Kanıt (long-only, gw=7, zw=30, cost=20bps gerçekçi)

| Metrik | Strateji | Buy-and-hold |
|---|---|---|
| Net getiri | **+272%** | +15.7% |
| Sharpe | **+1.25** | +0.40 |
| Pozisyon değişimi | 134 / 1095 gün (düşük turnover) | — |

**Geçtiği dürüstlük kapıları:**
1. **Parametre platosu** — gw=7-14, zw=30-60 hepsi buy-hold'u eziyor (long-only +135%…+326%).
   gw=3 (gürültü) ve gw=30 (zayıf) başarısız → tek şanslı nokta değil, ekonomik anlamlı plato
   (1-2 haftalık minting trendi).
2. **Maliyet dayanıklı** — 30bps round-trip'te bile +158%…+225%.
3. **Per-fold tutarlı** — 5/6 walk-forward fold buy-hold'u yeniyor; getiri zamana yayılı:
   - f0 −8.9% vs −26.1% ✓ | f1 +134.8% vs +108.6% ✓ | f2 +15.0% vs −24.6% ✓
   - f3 0.0% vs −35.8% ✓ | f4 +46.2% vs +144.4% ✗ (fazla defansif) | f5 +3.5% vs −42.3% ✓
   - Değer mekanizması: yukarıyı yakala + büyük drawdown'lardan kaç.
4. **Falsifikasyon (fiyat-momentum)** — aynı pipeline ETH fiyat-momentumuyla = **−57%, Sharpe
   −0.48, 1/6 IC fold.** Stablecoin sinyali fiyat-trendinden AYRI ve gerçek; sadece rejim filtresi
   değil. (Faz 1'i de teyit: fiyat-momentum OOS edge'siz.)
5. **Overall IC** = +0.060, p=0.046 (anlamlı). Per-fold IC çoğu tek başına anlamlı değil →
   değer günlük sıralamadan çok rejim-zamanlaması/drawdown kaçınması.

## Dürüst uyarılar (overselling yok)

- Tek varlık (ETH), tek 3-yıllık pencere (bir döngü). **Out-of-cycle / başka varlık teyidi şart.**
- DefiLlama gün-i arzının gün-i kapanışında bilindiği varsayımı (raporlama gecikmesi riski düşük ama var).
- Backtest idealize: günlük close'da execution, gerçek DEX likidite/MEV yok. Base'de günlük
  ETH/USDC rebalansı ucuz/gerçekçi ama canlı sürtünme marjı yer.
- **Canlı para DEĞİL.** Bu, OOS+maliyet barını geçen ilk sinyal; canlı için teyit + operatör onayı.

## Sıradaki hamleler (öncelik)

1. **Out-of-cycle teyit:** başka varlık (BTC) ve/veya daha uzun/farklı pencere; mümkünse
   chain-bazlı stablecoin arzı (Base/ETH'e özgü) DefiLlama'dan.
2. **Paper motoruna bağla:** ölü LGBM sinyalini bu sinyalle değiştir (shadow), forward track
   record biriktir (Faz 3). paper_decisions dolsun, ileri-doğru OOS.
3. Reddedersek dürüstçe yaz; geçerse → operatöre kanıtla, canlı kararı operatörün.
