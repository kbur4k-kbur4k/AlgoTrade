# CARRY_FINDINGS.md — Delta-nötr funding carry (edge arayışının TEK hayatta kalanı)

_Tarih: 2026-06-28 · Reproduce: `python -m scripts.validate_carry_edge`_

## Neden farklı

Önceki 5 sınıf hepsi YÖN bahsiydi (fiyatı tahmin et, buy-and-hold'u yen) → verimli
piyasa + maliyet + survivorship hepsini öldürdü. Carry kategorik olarak farklı:
**market-nötr getiri hasadı, yön tahmini YOK.**

Trade: long spot ETH + short eşit-notional perp ETH. Fiyat hareketleri birbirini
götürür (delta-nötr); short perp açıkken funding ALIRSIN (rate>0 iken perp long'lar
short'lara öder). Kripto funding zamanın %86'sında pozitif → yapısal pozitif carry.

## Kanıt (Binance ETHUSDT funding tam tarih, 2019-11 → 2026-06, 6.6 yıl)

| Dönem | Ort. funding/8h | %poz | NET yıllık | Sharpe* |
|---|---|---|---|---|
| **Tam 2019-2026** | 0.0129% | 86% | **+14.1%** | (yanıltıcı yüksek) |
| 2024-2026 | 0.0066% | 84% | +7.2% | — |
| **2025-2026** | 0.0031% | 75% | **+3.3%** | — |

- **Her dönem POZİTİF.** Per-fold (6 fold, 2019-2026): +2.2%…+34.4%, hiç kayıp yıl yok,
  4/6 risk-free'i (~%5) geçiyor. Tam-örnek kümülatif +153%.
- Benchmark = risk-free (~%4-5), buy-and-hold DEĞİL (market-nötr olduğu için).

(*) Script Sharpe ~15 verdi ama **YANILTICI**: gerçek risk funding oynaklığında değil —
likidasyon, basis slippage, karşı-taraf, depeg tail'inde. Sharpe'a güvenme.

## Dürüst caveat'lar (gerçek net daha düşük)

1. **Çürüyor.** %14 (tarihsel) → %7 (2yıl) → **%3.3 (son yıl).** Piyasa olgunlaştı,
   carry inceliyor. Güncel rejimde risk-free'in ucu ucunda.
2. **Modellenmeyen sürtünmeler:** basis slippage (giriş/çıkış), likidasyon tamponu
   maliyeti, borrow limitleri, exchange/karşı-taraf riski. Net bunların altında.
3. **Tail riski:** çöküşte funding sert negatife dönebilir + likidasyon riski.
4. **Operasyonel uyumsuzluk:** bu bot DeFi-spot Base cüzdanı; carry için türev hesabı +
   margin/likidasyon yönetimi + gerçek sermaye gerek = TAMAMEN farklı kurulum.

## Verdict

**Edge arayışının tek hayatta kalanı: gerçek, yapısal, her-dönem-pozitif — AMA çürüyen
ve güncel rejimde marjinal (~risk-free).** Yön-tahmini ölümünü aşan ilk mekanizma.
ANCAK canlıya geçiş türev-hesabı + gerçek sermaye + infra değişikliği gerektirir →
bu **operatör kararı** (DEĞİŞMEZ KURAL: canlı kapalı, gerçek para operatör onayı).

Otonom olarak yapılabilecek son şey bu raporu üretmek. Sıradaki adım operatörün:
gerçek-sürtünme due-diligence + sermaye/infra kararı, VEYA paper-track-record kurup
forward gözlem. Ben gerçek para/türev pozisyonu açmam.
