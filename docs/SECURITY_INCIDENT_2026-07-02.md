# GÜVENLİK OLAYI — 2026-07-02: sırlar git'e commit'lenmişti

## Ne bulundu (tam denetim taraması)

Repo geçmişinde (initial commit'ten beri) ve GitHub'da (private repo) **gerçek sırlar**:

| Dosya | İçerik | Durum |
|---|---|---|
| `deployment/k8s/secret.yaml` | VAULT_KEY, Telegram bot token, Alchemy key, Infura key (düz metin) | HEAD'den çıkarıldı, gitignore'da |
| `deployment/k8s/wallets-secret.yaml` | "Ana trading cüzdanı" `0x1F01...50f8` — private key vault-şifreli AMA VAULT_KEY yukarıdaki dosyada → birlikte çözülebilir | HEAD'den çıkarıldı, gitignore'da |
| `oci_retry.py` | Aynı Telegram token hardcoded | HEAD'den çıkarıldı, gitignore'da |

## Maruziyet değerlendirmesi

- Repo **private** (github.com/kbur4k-kbur4k/AlgoTrade) → maruziyet: GitHub + repo erişimi olanlar.
- Cüzdan `0x1F018cB72ac5520132B0b8221D0567a1fB8550f8` Base'de kontrol edildi (2026-07-02):
  **ETH = 0.0, USDC = 0.0 — BOŞ. Fon riski YOK.**
- Not: `run_local_paper.py` içindeki `0xac09...ff80` sorun DEĞİL — herkesçe bilinen
  Hardhat/Anvil test anahtarı #0, kasıtlı paper-burner.

## Yapılan (Claude, bu commit)

Üç dosya `git rm --cached` ile HEAD'den çıkarıldı (disk kopyaları lokal duruyor,
bot lokal çalışmaya devam edebilir), `.gitignore`'a eklendi → yeniden commit imkânsız.

## ⚠️ OPERATÖRÜN YAPMASI GEREKENLER (sırayla, ~10 dk)

Sır bir kez sızdıysa tek gerçek çare **rotasyon** — dosya silmek yetmez (git geçmişinde durur):

1. **Telegram bot token**: BotFather → `/mybots` → bot seç → API Token → **Revoke**.
   Yeni token'ı SADECE lokal `.env`'e yaz.
2. **Alchemy key** (`Qsdb...38TM`): dashboard.alchemy.com → app → API key **Regenerate**.
3. **Infura key** (`c380...9a32`): app.infura.io → key **sil/yenile**.
4. **VAULT_KEY + cüzdan**: cüzdan boş → en temizi bu cüzdanı TERK et; ileride gerekirse
   temiz makinede yeni cüzdan + yeni VAULT_KEY üret. Eski anahtarı hiçbir yerde kullanma.
5. **(Opsiyonel) Git geçmişi temizliği**: sırlar hâlâ ESKİ commit'lerde. Private repo +
   rotasyon sonrası pratik risk ~0; yine de istersen geçmiş yeniden yazılabilir
   (`git filter-repo` + force push = YIKICI işlem → Claude bunu ancak senin açık
   onayınla yapar; rotasyonu yaptıysan şart değil).

## Ders (kalıcı)

Sır yönetimi tek yol: `.env` (gitignore'lu) + `*.example` şablonlar. k8s/deploy
manifest'lerine gerçek değer ASLA yazılmaz. Bu kural CLAUDE.md DEĞİŞMEZ KURALLAR'da
zaten vardı; ihlal initial commit'ten miras geldi ve bu denetimde yakalandı.
