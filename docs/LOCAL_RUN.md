# Lokal Paper Çalıştırma

## Hızlı başlangıç

```bash
cp .env.local.example .env.local      # düzenleme şart değil; paper için boş secret yeterli
python scripts/run_local_paper.py     # ~60s smoke; "[smoke] PASS" görmelisin
```

`run_local_paper.py` ilk çalıştırmada bir burner paper cüzdanı (`wallets.local.json`,
fonlanmamış, sadece simülasyon) oluşturur. **Gerçek para/anahtar GEREKMEZ.**

Headless çalışır: Telegram credentials yoksa no-op notifier kullanılır
(bildirimler kapalı), bot yine de paper döngüsünü tamamlar.

## Sürekli paper çalıştırma

```bash
set -a; source .env.local; set +a
KMP_DUPLICATE_LIB_OK=TRUE python -m wallet_manager.orchestrator
```

Durdurmak için Ctrl-C. Mod `robust_paper`; canlı trading kapalı.

## Ortam notları

- Python 3.12 ortamı kullanılıyor; `pip install -r requirements.txt` + dev için
  `pytest pytest-asyncio pytest-mock pytest-cov aioresponses`.
- Bilinen açık bug (Faz 1'de düzeltilecek): paper engine cycle
  `OperationalError: no such column: session_id` ile atlanıyor → paper trade
  kaydedilmiyor. Olası migration: `scripts/add_session_id.py`.
