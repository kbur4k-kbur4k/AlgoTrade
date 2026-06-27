# STATUS.md — güncel durum

_Son güncelleme: 2026-06-28_

## 🎯 EN ÖNEMLİ: İlk geçen edge bulundu
**Stablecoin-supply sinyali** OOS + maliyet barını geçti (docs/ONCHAIN_FINDINGS.md):
long-only +272% vs buy-hold +15.7%, Sharpe 1.25 vs 0.40, 5/6 fold, fiyat-momentum
falsifikasyonunu geçti. Aday monetize-edilebilir edge. HÂLÂ PAPER — canlı için
out-of-cycle teyit + operatör onayı şart.

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

## Kanıtlanmış ölü yollar (tekrar deneme) ⛔
- OHLCV + LGBM/momentum: maliyet sonrası buy-and-hold yenmiyor (docs/FAZ1_FINDINGS.md).
- Funding-rate zscore mean-reversion (8sa): gerçekçi maliyette −55% (LEARNINGS.md).
- CEX exchange-flow (CryptoCompare): ücretli key → şimdilik bloke, ölü değil.

## Sıradaki en yüksek-etki hamle 🎯
**Stablecoin edge'ini sağlamlaştır + paper'a bağla:**
1. Out-of-cycle teyit: BTC ve/veya farklı pencere; mümkünse Base/ETH-özgü chain
   stablecoin arzı (DefiLlama chain endpoint).
2. Ölü LGBM sinyalini bu sinyalle değiştir (shadow) → forward track record (Faz 3),
   paper_decisions dolsun, ileri-doğru OOS doğrulama.
3. Geçmeye devam ederse → operatöre kanıtla; canlı kararı operatörün (DEĞİŞMEZ KURAL).

## Süreklilik notu
İkinci öncelik: birkaç saatte bir headless `claude -p` koşan Windows zamanlanmış
görev kur (CLAUDE.md SÜREKLİLİK). Gerçek para ASLA otomatik tetiklenmez.
