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

## 2026-06-28 — On-chain stablecoin-supply: İLK GEÇEN EDGE ✅

CEX exchange-flow (onchain_flows.py) ücretli key gerekti (CryptoCompare 401) → BLOKE.
Aynı tezin bedava vekili test edildi: toplam stablecoin arzı = dry powder.
Hipotez: arz büyür → alım gücü girer → ETH bullish. Günlük horizon (maliyet-OK).

Test: `scripts/validate_onchain_edge.py` — DefiLlama stablecoin arzı (free) + yerel
candle günlük close, 1096 gün (2023-04→2026-04). Causal zscore sinyali.

**VERDICT: aday monetize-edilebilir edge (OOS+maliyet barını geçen İLK sinyal).**
Long-only gw=7/zw=30/20bps: **+272% vs buy-hold +15.7%, Sharpe 1.25 vs 0.40.**
Geçtiği kapılar: (1) parametre platosu gw=7-14/zw=30-60 hepsi yener, gw=3/30 başarısız;
(2) 30bps'te bile yener; (3) 5/6 fold buy-hold'u yener (zamana yayılı); (4) FALSİFİKASYON:
fiyat-momentum aynı pipeline = −57% Sharpe −0.48 → stablecoin sinyali fiyattan AYRI/gerçek;
(5) overall IC +0.060 p=0.046. Mekanizma: yukarıyı yakala + drawdown'dan kaç.
Detay: docs/ONCHAIN_FINDINGS.md.
UYARI: tek varlık/tek döngü; out-of-cycle teyit + operatör onayı olmadan canlı YOK.

SIRADAKİ ALFA YOLLARI (öncelik):
1. **Stablecoin edge'i teyit + paper'a bağla** ← en yüksek etki. Out-of-cycle (BTC/başka
   pencere) + ölü LGBM yerine bu sinyali shadow'a koy, forward track record (Faz 3).
2. on-chain exchange net flow — CryptoCompare ücretli; bedava kaynak (Glassnode/CryptoQuant
   ücretli) bulunursa. ŞİMDİLİK bloke.
3. order-book OFI — tarihsel data YOK (sadece canlı) → forward-test.
4. funding carry (düşük turnover) — zscore mean-rev versiyonu öldü.
