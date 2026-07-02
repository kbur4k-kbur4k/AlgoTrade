# ROADMAP.md — Son Yol Haritası

_2026-07-02 · Bu dosya MASTER_ROADMAP V1-V4'ün ve tüm faz dokümanlarının yerine geçer.
V6 olmayacak. Değişiklik sadece TETİK ateşlenince yapılır, moda/heves değişince değil._

## Yeni kimlik (komple değişim)

Bu proje artık "inşa hâlindeki alfa botu" DEĞİL. Kanıt tamamlandı (docs/EDGE_SEARCH_SUMMARY.md):
bedava veriyle yön-tahmini ölü, tek yapısal getiri (carry) döngüsel ve şu an ince.

Yeni kimlik: **GÖZCÜ KULESİ + LABORATUVAR.**
- Gözcü: carry rejimini bedavaya izler, şişmanlayınca haber verir.
- Lab: herhangi bir yeni fikri ~1 saatte dürüstçe öldürür ya da yükseltir (validate_*_edge.py).
- Operatör eforu: **ayda 1 kısa rapor okumak. Hepsi bu.**

---

## FAZ A — Kapanış & Konsolidasyon (bu hafta, Claude yapar)

- [x] Eski roadmap/faz dokümanları → `docs/archive/` (silinmez, git'te geri alınabilir).
- [x] Bu dosya yazıldı; tek sayfa, kesin.
- [x] README yeni kimliğe göre güncellendi (gözcü+lab; alfa-botu iddiası kalktı).
- [x] Konsolidasyon: CLAUDE.md güncel, kırık test yok (66+ yeşil), tracker test altında,
      **T1 tetiği otomatik** (tracker her koşuda kontrol eder; ateşlenirse `T1_ALERT.md` yazar).
- [ ] Operatör tek komut çalıştırır (isteğe bağlı, bedava izleme için):
      `powershell -ExecutionPolicy Bypass -File scripts\setup_carry_schedule.ps1`
- Paper-loop KAPALI kalır: ölü sinyalle bot koşturmak israf. Sadece tracker koşar.

## FAZ B — Nöbet (süresiz, otomatik, operatör eforu ~0)

- Tracker her 8 saatte funding kaydeder (`carry_track.db`, bedava, API-masrafsız).
- Ayda 1: Claude kısa STATUS raporu — carry yıllıklandırılmış %, rejim, tek cümle verdict.
- **Geliştirme YOK. Yeni feature YOK. Yeni roadmap YOK.**

## FAZ C — Tetikler (tarih değil, OLAY güdümlü)

| Tetik | Koşul | Aksiyon |
|---|---|---|
| **T1 — Şişman carry** | 4+ hafta sürekli >%15 yıllık funding | Operatöre bildirim → türev hesabı + sermaye kararı OPERATÖRÜN → evetse 2 hafta paper-doğrulama → ancak ondan sonra küçük pilot (açık onayla) |
| **T2 — Sermaye eşiği** | Sermaye ~$50k+ (veya operatörün belirlediği eşik) | Ücretli-veri ar-ge yeniden açılır (aylık bütçe operatörden; her sinyal kill-test barından geçer) |
| **T3 — Yeni fikir** | Operatörden ya da Claude'dan fikir gelirse | 1 saatlik kill-test → sonuç LEARNINGS.md'ye → geçerse konuşulur, geçmezse biter |
| **T4 — Sessizlik** | 12 ay hiçbir tetik ateşlenmezse | Yıllık gözden geçirme: devam / arşiv kararı birlikte |

## Değişmez ilkeler

1. Kanıtsız hiçbir şey canlıya yaklaşmaz; gerçek para = yalnız operatör onayı (CLAUDE.md).
2. Tek sayfa kuralı: bu harita büyürse hastalık geri dönmüş demektir.
3. Ölü yollar geri açılmaz: OHLCV-ML, funding mean-rev, stablecoin-timing, xsec-momentum,
   sentiment, "endeks ürünü" — kanıt dosyalı (docs/*_FINDINGS.md).
4. Her kayıt dürüst: kazanmıyorsak "kazanmıyoruz" yazar.

## Uzun vade (asimptot — söz değil, yön)

Medallion-yönü ancak şu merdivenle: ilk kanıtlı edge (aday: T1 şişman carry) → küçük
gerçek kâr → kâr veriye/altyapıya yatar (T2) → sinyal genişler. Basamak atlanamaz;
her basamak kanıt-kapılı. Bu haritada hedef tarihi yok çünkü tetikler piyasanın elinde —
bizim elimizde olan tek şey hazır ve dürüst olmak.
