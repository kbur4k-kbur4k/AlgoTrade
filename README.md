# WalletBot — Gözcü Kulesi + Laboratuvar

> Bu repo bir "piyasayı yenen trading botu" **değildir.** Öyle bir şey bulamadık —
> ve bunu kanıtlarıyla söylüyoruz. Bu repo, o sorunun dürüstçe cevaplanmış hâlidir:
> bir **rejim gözcüsü** (carry izleyici) + bir **doğrulama laboratuvarı** (edge kill-test
> makinesi) + arşivlenmiş, çalışan bir paper-trading altyapısı.

## Ne var burada

| Parça | Ne işe yarar | Durum |
|---|---|---|
| **[ROADMAP.md](ROADMAP.md)** | Tek geçerli harita (olay-güdümlü, tek sayfa) | Aktif |
| **[STATUS.md](STATUS.md)** | Ne çalışıyor, ne bekliyor | Aktif |
| **[LEARNINGS.md](LEARNINGS.md)** | Kanıt günlüğü — hangi yol neden öldü | Aktif |
| `scripts/carry_tracker.py` | Delta-nötr funding carry'nin bedava ileri-doğru izleyicisi | **Nöbette** |
| `scripts/validate_*_edge.py` | 6 dürüst edge kill-test harness'ı (maliyet + out-of-cycle + falsifikasyon) | Lab |
| `wallet_manager/` | 55k satır paper-trading altyapısı (Base, robust_paper) | Dondurulmuş |
| `docs/*_FINDINGS.md` | Araştırma kanıtları | Kapanmış |

## Çekirdek bulgu (docs/EDGE_SEARCH_SUMMARY.md)

6 alfa sınıfı maliyet-dahil + out-of-cycle (farklı dönem VE varlık) test edildi:

- **5 yön-tahmini sınıfı ÖLÜ:** OHLCV+ML, funding mean-reversion, on-chain stablecoin-supply,
  cross-sectional momentum, sentiment. Hiçbiri maliyet sonrası buy-and-hold'u yenemedi.
- **1 hayatta kalan:** delta-nötr funding **carry** (long spot + short perp) — yapısal,
  2019-2026 her yıl pozitif, tarihsel +%14/yıl; ama döngüsel ve şu an ince (~%1-3).
  Tracker tam bu yüzden nöbette: rejim şişmanlayınca (>%15/yıl) operatöre haber verir.

**Metodoloji dersi (bu reponun asıl değeri):** tek pencerede walk-forward = sahte güven.
Gerçek OOS = farklı dönem VE farklı varlık. İki "harika görünen" sinyal bu barla yakalandı
ve dürüstçe reddedildi. Yeni her fikir aynı bardan geçer (~1 saat).

## Hızlı başlangıç

```bash
# bağımlılıklar (Python 3.12; py 3.14 KULLANMA — torch yok)
pip install -r requirements.lock.txt

# carry izleyiciyi bir kez çalıştır
python -m scripts.carry_tracker

# 8 saatte bir otomatik izleme (opsiyonel, bedava; operatör kurar)
powershell -ExecutionPolicy Bypass -File scripts\setup_carry_schedule.ps1

# lab: herhangi bir edge fikrini dürüstçe test et (örnekler)
python -m scripts.validate_carry_edge --cost-bps 8
python scripts/validate_xsectional_edge.py --lookback 30 --top-k 5 --from-ym 2023-01

# dondurulmuş paper-bot'u lokalde koşturmak istersen (gerekli değil)
python scripts/run_local_paper.py

# testler — HEDEFLİ koş (tam suite asılı kalabiliyor / 5GB+ RAM)
python -m pytest tests/unit/test_carry_tracker.py -q
```

## Değişmez kurallar

- **Canlı trading KAPALI.** Gerçek para yalnız: kanıtlı edge + operatörün açık onayı.
- Sırlar (.env, cüzdan anahtarları) asla log'lanmaz/commit'lenmez.
- Her değişiklik küçük, geri alınabilir commit.
- Sonuç uydurulmaz: edge yoksa "yok" yazılır. Bu reponun tarihi bunun kanıtı —
  iki abartılı iddia yakalandı ve `git log`'da dürüstçe düzeltildi.

## Tetikler (ne olursa ne yapılır — ROADMAP.md FAZ C)

- **T1:** carry 4+ hafta >%15/yıl → operatöre "şişman rejim" bildirimi
- **T2:** sermaye eşiği aşılırsa → ücretli-veri ar-ge yeniden açılır
- **T3:** yeni fikir → 1 saatlik kill-test → LEARNINGS.md
- **T4:** 12 ay sessizlik → yıllık gözden geçirme
