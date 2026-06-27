# STATUS.md — güncel durum

_Son güncelleme: 2026-06-28_

## ⚠️ Düzeltme: stablecoin edge'i REDDEDİLDİ (out-of-cycle çöktü)
Stablecoin-supply sinyali in-window (2023-26 ETH) harika görünmüştü ama
out-of-cycle başarısız (ETH 2020-22: +7% vs buy-hold +890%; BTC: çok altında).
Overfit/rejim-özgü. Edge DEĞİL. Detay+metodoloji dersi: docs/ONCHAIN_FINDINGS.md.
DERS: tek 3-yıl penceresinde walk-forward = sahte güven; gerçek OOS = farklı
dönem VE varlık. Henüz monetize edilebilir edge YOK.

## Çalışıyor ✅
- Bot lokalde robust_paper modda koşuyor (Faz 0 smoke PASS).
- Chain config = Base mainnet (chain_id=8453). WRONG_CHAIN bug çözülmüş.
- session_id bug çözülmüş; paper_decisions gerçek session_id'lerle yazıyor.
- Validation harness'ları: `validate_ml_edge.py` (LGBM), `validate_funding_edge.py`
  (funding), `validate_onchain_edge.py` (stablecoin — EDGE BULAN).

## Bozuk / eksik ⚠️
- **Paper ölçüm üretmiyor:** paper_decisions=5, paper_trades=0. Sistem shadow_cycle'a
  ulaşıyor ama ölü LGBM sinyali her cycle reddediyor (HOLD/SKIPPED). Bu beklenen —
  LGBM Faz 1'de edge'siz; onu zorlamak yanlış. Gerçek iş = yeni alfa bul.
- Süreklilik düzeneği (zamanlanmış görev) henüz KURULMADI. CLAUDE.md istiyor.

## Kanıtlanmış ölü/yetersiz yollar (tekrar deneme) ⛔
- OHLCV + LGBM/momentum: maliyet sonrası buy-and-hold yenmiyor (docs/FAZ1_FINDINGS.md).
- Funding-rate zscore mean-reversion (8sa): gerçekçi maliyette −55% (LEARNINGS.md).
- Stablecoin-supply timing: in-window iyi, out-of-cycle çöktü → overfit (ONCHAIN_FINDINGS.md).
- Cross-sectional momentum: gerçek faktör ama ÇÜRÜMÜŞ; 2023-25 EW-hold'a karşı edge~0,
  survivorship üst-sınır (docs/XSECTIONAL_FINDINGS.md).
- CEX exchange-flow (CryptoCompare): ücretli key → şimdilik bloke, ölü değil.

## Önemli yan bulgu (ürün açısı)
Equal-weight 17-coin sepet + haftalık rebalans, BTC-hold'u yendi: +1431% vs +930%,
Sharpe 1.15 vs 1.13 (2020-2025). Alfa değil — çeşitlendirme/rebalans primi, ama
sağlam ve savunulabilir bir ÜRÜN çekirdeği.

## Sıradaki en yüksek-etki hamle 🎯
3 alfa sınıfı denendi (price-ML, funding, on-chain-supply, xsec-momentum) → hiçbiri
canlı için net monetize edilebilir değil. İki yol:
1. **REFRAME (CLAUDE.md kapı-c, güçlü aday):** EW-rebalans çeşitlendirilmiş endeksi
   paper'da çalıştır, forward track record (Faz 3); operatörle "para kazanan tek-sinyal
   yerine sağlam endeks ürünü" konuşması. Bu ÖLÇÜ'nün sağlamlık yarısına hizmet eder.
2. Devam edersek son alfa kolu: order-book OFI (canlı kaydet→forward-test) — tek
   kalan, tarihsel-veri-gerektirmeyen mikroyapı yolu.
**Operatör kararı gerekiyor:** reframe mi, son alfa kolu mu?

## Süreklilik notu
İkinci öncelik: birkaç saatte bir headless `claude -p` koşan Windows zamanlanmış
görev kur (CLAUDE.md SÜREKLİLİK). Gerçek para ASLA otomatik tetiklenmez.
