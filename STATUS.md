# STATUS.md — güncel durum

_Son güncelleme: 2026-06-28_

## Çalışıyor ✅
- Bot lokalde robust_paper modda koşuyor (Faz 0 smoke PASS).
- Chain config = Base mainnet (chain_id=8453). WRONG_CHAIN bug çözülmüş.
- session_id bug çözülmüş; paper_decisions gerçek session_id'lerle yazıyor.
- Faz 1 validation harness'ları: `scripts/validate_ml_edge.py` (LGBM),
  `scripts/validate_funding_edge.py` (funding — YENİ).

## Bozuk / eksik ⚠️
- **Paper ölçüm üretmiyor:** paper_decisions=5, paper_trades=0. Sistem shadow_cycle'a
  ulaşıyor ama ölü LGBM sinyali her cycle reddediyor (HOLD/SKIPPED). Bu beklenen —
  LGBM Faz 1'de edge'siz; onu zorlamak yanlış. Gerçek iş = yeni alfa bul.
- Süreklilik düzeneği (zamanlanmış görev) henüz KURULMADI. CLAUDE.md istiyor.

## Kanıtlanmış ölü yollar (tekrar deneme) ⛔
- OHLCV + LGBM/momentum: maliyet sonrası buy-and-hold yenmiyor (docs/FAZ1_FINDINGS.md).
- Funding-rate zscore mean-reversion (8sa): gerçekçi maliyette −55% (LEARNINGS.md).

## Sıradaki en yüksek-etki hamle 🎯
**On-chain exchange net flow sinyalini Faz 1 disipliniyle OOS test et**
(wallet_manager/data/onchain_flows.py). Projenin en savunulabilir veri avantajı.
Adımlar: CryptoCompare'den tarihsel saatlik flow çek → ETH forward return ile
hizala → walk-forward IC + maliyet-dahil backtest → dürüst verdict.
Net buy-and-hold yenerse: edge bulundu. Yenmezse: logla, sıradaki yol.

## Süreklilik notu
İkinci öncelik: birkaç saatte bir headless `claude -p` koşan Windows zamanlanmış
görev kur (CLAUDE.md SÜREKLİLİK). Gerçek para ASLA otomatik tetiklenmez.
