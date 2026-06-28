# EDGE_SEARCH_SUMMARY.md — alfa arayışı konsolide verdict

_Tarih: 2026-06-28 · Tüm testler maliyet-dahil + out-of-cycle disiplinli._

## Çekirdek sonuç

**6 alfa sınıfı rigörlü test edildi. 5 YÖN-tahmini sınıfının hiçbiri maliyet +
out-of-cycle sonrası buy-and-hold'u yenmedi. TEK hayatta kalan: delta-nötr funding
CARRY (market-nötr, yön tahmini değil) — gerçek ama çürüyen, ve canlıya geçişi
operatör kararı (türev hesabı + gerçek sermaye).**

| # | Alfa sınıfı | Veri (bedava) | Verdict | Belge |
|---|---|---|---|---|
| 1 | OHLCV + LightGBM/momentum | yerel candle | Edge 5dk'da var, maliyet yiyor; uzun horizonda edge yok | FAZ1_FINDINGS.md |
| 2 | Funding-rate mean-reversion | Binance funding | 10bps'te −55%; edge yok | commit 92c7c3a |
| 3 | On-chain stablecoin-supply | DefiLlama | In-window harika, out-of-cycle ÇÖKTÜ (overfit) | ONCHAIN_FINDINGS.md |
| 4 | Cross-sectional momentum | Binance panel | Gerçek faktör ama ÇÜRÜMÜŞ; 2023-25 edge~0; survivorship | XSECTIONAL_FINDINGS.md |
| 5 | Sentiment (Fear & Greed) | alternative.me | Her dilimde ölü; IC negatif | commit 91ff9f9 |
| 6 | **Delta-nötr funding CARRY** | Binance funding | **HAYATTA KALAN: market-nötr, her dönem pozitif (+14% tarihsel) AMA çürüyor (→%3.3 son yıl, ~risk-free) + türev infra gerek** | CARRY_FINDINGS.md |

Ek: "çeşitlendirilmiş EW endeks" konsolasyonu da çöktü — rebalans primi ≈0; güncel
rejimde yalın BTC-hold (Sharpe 1.85) çeşitlendirilmiş sepeti (0.92) eziyor.

## Carry detay (#6) — neden ayrı kategori

İlk 5 "fiyatı tahmin et". Carry tahmin etmez: long spot + short perp, funding hasat
eder (rate>0 %86 zaman). 2019-2026 her fold pozitif (+2.2%…+34.4%), net +14.1%/yıl
tarihsel. AMA: çürüyor (%14→%7→%3.3), Sharpe yanıltıcı (risk funding oynaklığında
değil tail'de), türev hesabı+gerçek sermaye+likidasyon yönetimi gerek = operatör kararı.
Bu, "yön bahsi" ölümünü aşan gerçekten farklı yol (PUSULA #3) — körü körüne zorlama değil.

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

"Asla pes etme AMA körü körüne de zorlama." 5 yön-tahmini sınıfı reddedildikten sonra
6. olarak kategorik-farklı carry denendi (PUSULA #3: "sebebi aşan gerçekten farklı yol")
→ tek hayatta kalan. Daha fazla yön-tahmini zorlamak körlük olur. Kalan yollar artık
operatör girdisi gerektirir (ÖLÇÜ'yü değiştiremem, parayı izinsiz harcayamam):

**A. Carry'yi ciddiye al (en yüksek EV):** gerçek-sürtünme due-diligence (basis,
   likidasyon, karşı-taraf) + türev hesabı/sermaye kararı operatörün. Paper forward-track
   kurulabilir. UYARI: çürüyor, güncel ~risk-free; küçük sermaye için zahmete değmeyebilir.
B. Ücretli alt-veri (Glassnode/CryptoQuant smart-money flow) — bütçe kararı.
C. Order-book OFI — canlı kayıt infra; Faz 1 maliyet uyarısı → düşük umut.
D. Beklenti reframe (kapı-c) — ÖLÇÜ değişikliği, operatör kararı.
E. Dürüst duraklat — sistemi sağlam/paper bırak, periyodik gözden geçir.

Sağlamlık (ÖLÇÜ yarı-2) sağlanmış: bot paper'da çalışıyor, chain/session bug'ları
çözülü, validation harness hazır. Yalan yok: yön-tahmininde kanıtlı edge yok; tek
yapısal getiri (carry) gerçek ama marjinal+infra-bağımlı.
