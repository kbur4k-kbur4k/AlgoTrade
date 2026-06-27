# EDGE_SEARCH_SUMMARY.md — alfa arayışı konsolide verdict

_Tarih: 2026-06-28 · Tüm testler maliyet-dahil + out-of-cycle disiplinli._

## Çekirdek sonuç

**5 alfa sınıfı rigörlü test edildi; hiçbiri maliyet + out-of-cycle (farklı dönem VE
varlık) sonrası basit buy-and-hold'u (baskın varlık) net yenmedi.** Bu kurulumda
(küçük sermaye, on-chain maliyet, bedava veri) kanıtlı monetize-edilebilir edge yok.

| # | Alfa sınıfı | Veri (bedava) | Verdict | Belge |
|---|---|---|---|---|
| 1 | OHLCV + LightGBM/momentum | yerel candle | Edge 5dk'da var, maliyet yiyor; uzun horizonda edge yok | FAZ1_FINDINGS.md |
| 2 | Funding-rate mean-reversion | Binance funding | 10bps'te −55%; edge yok | LEARNINGS.md / commit 92c7c3a |
| 3 | On-chain stablecoin-supply | DefiLlama | In-window harika, out-of-cycle ÇÖKTÜ (overfit) | ONCHAIN_FINDINGS.md |
| 4 | Cross-sectional momentum | Binance panel | Gerçek faktör ama ÇÜRÜMÜŞ; 2023-25 edge~0; survivorship | XSECTIONAL_FINDINGS.md |
| 5 | Sentiment (Fear & Greed) | alternative.me | Her dilimde ölü; IC negatif; −99%…−40% vs +bh | bu belge / commit (sentiment) |

Ek: "çeşitlendirilmiş EW endeks" konsolasyonu da çöktü — rebalans primi ≈0; güncel
rejimde yalın BTC-hold (Sharpe 1.85) çeşitlendirilmiş sepeti (0.92) eziyor.

## Sentiment detay (#5)

Kontraryan hipotez (aşırı korku=al). Long-only, zscore, 20bps:
- ETH full: strateji −99% vs buy-hold +51%, IC −0.03, 0/6 fold.
- BTC late 2023-26: −40% vs **+261% (Sharpe 1.02)**, 1/6 fold.
- Hem ETH hem BTC, hem erken hem geç → tutarlı başarısızlık.
- Günlük ölçekte F&G kontraryan reversion yok (korku→korku); net negatif.

## Metodoloji kazanımı (kalıcı değer)

Yeniden kullanılabilir, dürüst doğrulama makinesi kuruldu — her aday edge için:
maliyet-dahil + **out-of-cycle (farklı dönem VE varlık)** + falsifikasyon benchmark +
per-fold tutarlılık + survivorship farkındalığı. Scriptler: `scripts/validate_*_edge.py`.
KRİTİK DERS: tek pencerede walk-forward = sahte güven (#3 bunu kanıtladı).

## Karar gerekçesi (CLAUDE.md)

"Asla pes etme AMA körü körüne de zorlama." 5 sınıf rigörlü reddedildikten sonra
6. spekülatif bedava-alfayı zorlamak körlüktür. Gerçekten farklı VE +EV kalan yollar
operatör girdisi gerektirir (ÖLÇÜ'yü ben değiştiremem, parayı izinsiz harcayamam):
1. Ücretli alt-veri (Glassnode/CryptoQuant smart-money flow) — bütçe kararı.
2. Order-book OFI — canlı kayıt infra; Faz 1 maliyet uyarısı → düşük umut.
3. Beklenti reframe (kapı-c) — ÖLÇÜ değişikliği, operatör kararı.
4. Dürüst duraklat — sistemi sağlam/paper bırak, periyodik gözden geçir.

Sağlamlık (ÖLÇÜ yarı-2) sağlanmış durumda: bot paper'da çalışıyor, chain/session
bug'ları çözülü, validation harness hazır. Yalan yok: kanıtlı edge yok.
