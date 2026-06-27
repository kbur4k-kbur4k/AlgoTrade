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

## Kanıtlanmış ölü yollar (tekrar deneme) ⛔
- OHLCV + LGBM/momentum: maliyet sonrası buy-and-hold yenmiyor (docs/FAZ1_FINDINGS.md).
- Funding-rate zscore mean-reversion (8sa): gerçekçi maliyette −55% (LEARNINGS.md).
- Stablecoin-supply timing: in-window iyi, out-of-cycle çöktü → overfit (ONCHAIN_FINDINGS.md).
- CEX exchange-flow (CryptoCompare): ücretli key → şimdilik bloke, ölü değil.

## Sıradaki en yüksek-etki hamle 🎯
Aday alfa yolları (out-of-cycle barıyla, yani farklı dönem+varlık):
1. Çok-varlık **cross-sectional** sinyal (varlıklar-arası sıralama; tek-varlık
   zamanlamanın overfit tuzağından kaçar) — farklı alfa sınıfı.
2. order-book OFI — tarihsel yok, canlı kaydet + forward-test.
3. Hiçbiri tutmazsa: CLAUDE.md kapı (c) — beklentiyi yeniden çerçevele
   (portföy/altyapı ürünü), operatörle konuş.

## Süreklilik notu
İkinci öncelik: birkaç saatte bir headless `claude -p` koşan Windows zamanlanmış
görev kur (CLAUDE.md SÜREKLİLİK). Gerçek para ASLA otomatik tetiklenmez.
