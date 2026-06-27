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

## "Endeks ürünü" yan bulgusu DA çürüdü (stress-test)
Rebalans primi ≈ 0; EW>BTC sadece 2020-22 alt-season+survivorship. Güncel rejimde
(2023-25) yalın BTC-hold (+558%, Sharpe 1.85) EW sepeti (+138%, 0.92) EZİYOR.
Çeşitlendirilmiş endeks bile out-of-cycle'da buy-and-hold'u yenmiyor.

## Çekirdek gerçek
4 alfa sınıfı (OHLCV-ML, funding, on-chain-supply, xsec-momentum) + endeks konsolasyonu →
HİÇBİRİ maliyet+out-of-cycle sonrası basit buy-and-hold'u (baskın varlık) net yenmiyor.
Faz 1'in sonucu genelleşti: bu kurulumda kanıtlı edge YOK.

## Sıradaki: STRATEJİK ÇATAL (operatör kararı) 🎯
CLAUDE.md "asla pes etme AMA körü körüne zorlama" — 5. spekülatif alfayı zorlamak körlük olur.
Operatöre sunulan seçenekler (kanıt: docs/*_FINDINGS.md):
1. **Reframe (kapı-c):** ürünü "buy-and-hold'u yenen bot" yerine başka bir değer önerisi
   olarak tanımla (risk-yönetimi/otomasyon/raporlama), gerçek-para hedefini bırak.
2. **Son alfa kolu:** order-book OFI (canlı kaydet→forward-test) — tek kalan data-hafif yol,
   ama Faz 1 mikroyapıda maliyetin edge'i yediğini gösterdi → düşük umut.
3. **Yeni veri sınıfı (para gerektirir):** ücretli on-chain (Glassnode/CryptoQuant) veya
   alternatif veri — operatör bütçe kararı.
4. **Dürüst duraklat:** kanıtlı edge yok; sistemi sağlam/paper bırak, periyodik gözden geçir.

## Süreklilik notu
İkinci öncelik: birkaç saatte bir headless `claude -p` koşan Windows zamanlanmış
görev kur (CLAUDE.md SÜREKLİLİK). Gerçek para ASLA otomatik tetiklenmez.
