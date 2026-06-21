# Faz 0 — Temizlik & Lokal Paper Çalıştırma — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repoyu ölü kod/çöpten arındır, bağımlılıkları sabitle ve botu lokalde paper-modda tek komutla bootlanabilir hale getir.

**Architecture:** İki bağımsız iş kümesi — (1) güvenli silme + sabitleme (saf temizlik), (2) secret'sız lokal paper smoke launcher. Hiçbir runtime davranışı değişmez; sadece ölü dosyalar gider ve yeni bir lokal-çalıştırma scaffolding'i eklenir.

**Tech Stack:** Python 3.11, git, pytest, web3, aiosqlite. Windows + git-bash/PowerShell.

---

## File Structure

- Sil: `wallet_manager/alerting.py` (paket tarafından gölgelenmiş ölü modül)
- Sil: `wallet_manager/task_factories_yield.py`, `_algo.py`, `_short.py`, `_airdrop.py` (saf re-export stub, hiç import edilmiyor)
- Sil (diskten): kök artıkları + `wallet_manager/ml_models/archive/`
- Değiştir: `requirements.txt` (sürüm pinleri)
- Oluştur: `requirements.lock.txt` (tam donmuş ortam)
- Oluştur: `.env.local.example` (paper env şablonu)
- Oluştur: `scripts/run_local_paper.py` (smoke launcher)
- Oluştur: `docs/LOCAL_RUN.md` (lokal çalıştırma talimatı)

---

### Task 1: Onaylanmış ölü kodu sil

**Files:**
- Delete: `wallet_manager/alerting.py`
- Delete: `wallet_manager/task_factories_yield.py`, `wallet_manager/task_factories_algo.py`, `wallet_manager/task_factories_short.py`, `wallet_manager/task_factories_airdrop.py`

- [ ] **Step 1: Hiçbir runtime/script kodunun bunları import etmediğini doğrula (silme öncesi güvenlik testi)**

Run:
```bash
grep -rn "task_factories_yield\|task_factories_algo\|task_factories_short\|task_factories_airdrop" wallet_manager scripts | grep -v "tests/"
grep -rn "from wallet_manager.alerting import\|import wallet_manager.alerting" wallet_manager scripts
```
Expected: `alerting` importları YALNIZCA `wallet_manager.alerting` paketini (`alerting/__init__.py`) çözer; `task_factories_*` stub'larına ait satır YOK (yalnızca tanımın kendisi). Bu, paketin `alerting.py`'yi gölgelediğini ve stub'ların yetim olduğunu teyit eder.

- [ ] **Step 2: Dosyaları sil**

```bash
git rm wallet_manager/alerting.py \
       wallet_manager/task_factories_yield.py \
       wallet_manager/task_factories_algo.py \
       wallet_manager/task_factories_short.py \
       wallet_manager/task_factories_airdrop.py
```

- [ ] **Step 3: Import sağlığı — orchestrator hâlâ yükleniyor mu**

Run:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python -c "import wallet_manager.orchestrator; from wallet_manager.alerting import get_alert_system; print('imports OK')"
```
Expected: `imports OK` (alerting paketi hâlâ `get_alert_system` veriyor; silinen modül gölgeydi).

- [ ] **Step 4: task_factories testlerini koş (silinen stub'lar testte geçiyordu — testler de güncellenmeli)**

Run:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python -m pytest tests/ -k "task_factories or alerting" -q --no-header 2>&1 | tail -20
```
Expected: Stub'lara özel testler FAIL/ERROR verebilir (silinen modülü import ediyorlar). Bu testleri sil ya da gerçek `task_factories`/`alerting` paketine yönlendir. Çekirdek `task_factories` testleri PASS kalmalı.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead code — shadowed alerting.py + 4 task_factories re-export stubs"
```

---

### Task 2: Disk artıklarını ve model arşivini temizle

**Files:**
- Delete (diskten): `coverage_result.txt`, `coverage_final.txt`, `final_cov_result.txt`, `collect_out.txt`, `test_boost_result.txt`, `wallet_manager.tar.gz`, `.coverage.*`
- Delete (diskten): `wallet_manager/ml_models/archive/` (3 nesil eski model kopyası + `.bak`)
- Delete (diskten): `*.db-shm`, `*.db-wal`

Not: Bunlar `.gitignore`'da zaten hariç (commit'lenmedi); yalnızca diskten kaldırılıyor.

- [ ] **Step 1: Artıkları sil**

```bash
rm -f coverage_result.txt coverage_final.txt final_cov_result.txt collect_out.txt test_boost_result.txt wallet_manager.tar.gz .coverage.* paper_trades.db-shm paper_trades.db-wal
rm -rf wallet_manager/ml_models/archive
```

- [ ] **Step 2: Aktif modellerin hâlâ yerinde olduğunu doğrula**

Run:
```bash
ls wallet_manager/ml_models/*.txt wallet_manager/ml_models/*.pt wallet_manager/ml_models/*.json
```
Expected: `lgbm_alpha_model.txt`, `lstm_alpha_model.pt`, `transformer_alpha_model.pt`, `ppo_risk_policy.pt`, `ppo_phase1_checkpoint.pt`, `xgb_alpha_model.json`, `training_report.json` — hepsi mevcut.

- [ ] **Step 3: Modellerin hâlâ yüklendiğini doğrula**

Run:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python -c "
import lightgbm as lgb, xgboost as xgb, torch
from pathlib import Path
D=Path('wallet_manager/ml_models')
lgb.Booster(model_file=str(D/'lgbm_alpha_model.txt'))
m=xgb.XGBClassifier(); m.load_model(str(D/'xgb_alpha_model.json'))
torch.jit.load(str(D/'transformer_alpha_model.pt'),map_location='cpu')
print('models load OK')
"
```
Expected: `models load OK`

- [ ] **Step 4: Commit (working tree temiz olduğunu kayda geç)**

```bash
git add -A
git status --short
git commit -m "chore: delete on-disk run artifacts and model archive" --allow-empty
```
Not: Bu dosyalar zaten gitignore'lu olduğundan commit boş olabilir; `--allow-empty` ile niyet kaydı bırakılır.

---

### Task 3: Bağımlılıkları sabitle

**Files:**
- Modify: `requirements.txt`
- Create: `requirements.lock.txt`

- [ ] **Step 1: Kurulu sürümleri tam dondur**

Run:
```bash
python -m pip freeze > requirements.lock.txt
```
Expected: `requirements.lock.txt` oluşur (numpy==2.4.4, pandas==3.0.2, xgboost==3.2.0, lightgbm==4.6.0, torch==2.5.1+cu121, web3==7.15.0, ... gibi tam sürümler).

- [ ] **Step 2: requirements.txt alt-sınırlarını kurulu sürümlere çek**

`requirements.txt` içindeki pinleri kurulu gerçeğe hizala (örnek — lock'tan teyit ederek doldur):
```
numpy>=2.4,<3
pandas>=3.0,<4
scipy>=1.17
scikit-learn>=1.8
xgboost>=3.2
lightgbm>=4.6
torch>=2.5
web3>=7.15,<8
aiohttp>=3.13
```
Diğer satırlar korunur. Amaç: kod hangi sürümle çalışıyorsa onu yansıt (eski `>=1.24`/`>=2.0` pinleri yanıltıcı).

- [ ] **Step 3: Doğrulama — import + tek targeted test**

Run:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python -c "import numpy,pandas,xgboost,lightgbm,torch,web3; print('deps import OK')"
KMP_DUPLICATE_LIB_OK=TRUE python -m pytest tests/unit/test_phase5_backtester.py -q --no-header 2>&1 | tail -10
```
Expected: `deps import OK`; backtester unit testleri PASS.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt requirements.lock.txt
git commit -m "chore: pin requirements to installed versions + add lock file"
```

---

### Task 4: Lokal paper smoke scaffolding

**Files:**
- Create: `.env.local.example`
- Create: `scripts/run_local_paper.py`
- Create: `docs/LOCAL_RUN.md`
- Modify: `.gitignore` (add `.env.local`, `wallets.local.json`)

- [ ] **Step 1: `.env.local.example` oluştur**

```bash
# Lokal paper-trading için minimum ortam. Kopyala: cp .env.local.example .env.local
EXECUTION_MODE=robust_paper
PAPER_TRADE=true
PAPER_INITIAL_BALANCE_USD=140.0
WALLET_CONFIG_PATH=wallets.local.json

# Base RPC (public uç yeterli; sadece okuma)
BASE_RPC_1=https://mainnet.base.org
BASE_RPC_2=https://base.drpc.org

# Paper modda secret zorunlu değil; boş bırakılabilir
VAULT_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

LOG_LEVEL=INFO
METRICS_ENABLED=false
LIVE_TRADING_ENABLED=false
```

- [ ] **Step 2: `.gitignore`'a lokal dosyaları ekle**

`.gitignore` sonuna:
```
.env.local
wallets.local.json
```

- [ ] **Step 3: `scripts/run_local_paper.py` smoke launcher yaz**

Bot `while True` döngüsü olduğundan smoke testi alt-süreç + zaman sınırıyla koşar, başlangıç loglarını tarar, sonra sonlandırır. Başarı = paper döngüsüne çökensiz ulaşmak.

```python
"""Lokal paper smoke launcher.

Botu robust_paper modda secret'sız başlatır, ~45s çalıştırır, başlangıç
loglarını tarar ve sonlandırır. Edge/PnL ölçmez — sadece "bootlanıyor mu".

Kullanım:
    python scripts/run_local_paper.py            # 45s smoke
    python scripts/run_local_paper.py --seconds 90
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WALLETS = ROOT / "wallets.local.json"

# Hardhat test key #0 — KAMUYA AÇIK BURNER, ASLA FONLAMA. Sadece paper için.
_BURNER_PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def ensure_paper_wallet() -> None:
    if WALLETS.exists():
        return
    WALLETS.write_text(json.dumps([{
        "wallet_id": "paper_01",
        "address": "0x4200000000000000000000000000000000000006",
        "private_key": _BURNER_PK,
        "label": "Local paper wallet (burner, unfunded)",
        "rpc_url": "https://mainnet.base.org",
        "chain_id": 8453,
        "max_gas_price_gwei": 50.0,
        "enabled": True,
    }], indent=2))
    print(f"[smoke] created {WALLETS.name} (burner paper wallet)")


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "KMP_DUPLICATE_LIB_OK": "TRUE",
        "EXECUTION_MODE": "robust_paper",
        "PAPER_TRADE": "true",
        "PAPER_INITIAL_BALANCE_USD": "140.0",
        "WALLET_CONFIG_PATH": str(WALLETS),
        "BASE_RPC_1": "https://mainnet.base.org",
        "BASE_RPC_2": "https://base.drpc.org",
        "VAULT_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "METRICS_ENABLED": "false",
        "LIVE_TRADING_ENABLED": "false",
        "LOG_LEVEL": "INFO",
        "PYTHONUNBUFFERED": "1",
    })
    return env


SUCCESS_MARKERS = ("Orchestrator", "robust_paper", "paper")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=45)
    args = ap.parse_args()

    ensure_paper_wallet()
    print(f"[smoke] launching orchestrator for {args.seconds}s ...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "wallet_manager.orchestrator"],
        cwd=str(ROOT), env=build_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines: list[str] = []
    booted = False
    start = time.time()
    try:
        while time.time() - start < args.seconds:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                if proc.poll() is not None:
                    break
                continue
            sys.stdout.write(line)
            lines.append(line)
            if any(m in line for m in SUCCESS_MARKERS):
                booted = True
            if "Traceback" in line or "CRITICAL" in line:
                # erken çöküş; toplamaya devam
                pass
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    crashed = any("Traceback" in ln for ln in lines)
    if booted and not crashed:
        print("\n[smoke] PASS — orchestrator paper döngüsüne çökmeden ulaştı.")
        return 0
    print("\n[smoke] FAIL — bootlanamadı ya da çöktü. Yukarıdaki loga bak.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Smoke launcher'ı çalıştır (gerçek boot denemesi)**

Run:
```bash
python scripts/run_local_paper.py --seconds 45
```
Expected (ideal): `[smoke] PASS`.

**Bilinen olası engeller ve düzeltmeleri** (çıkarsa execution sırasında systematic-debugging skill ile uygulanır):
- `wallets.json: chain_id must be 8453 (Base).` → wallet config'te `chain_id: 8453` (launcher zaten 8453 yazıyor; başka chain_id=1 kaynağı varsa onu düzelt).
- `ConfigurationError: ... required field ... private_key` → wallet şeması `private_key` (düz) bekliyor; `encrypted_private_key` değil. Launcher düz `private_key` veriyor. ✓
- Telegram boş token'a takılırsa → paper modda Telegram'ı opsiyonel yapan guard ekle (kaynak: `telegram_*` init'i `if cfg.telegram_bot_token:` ile sarmala).
- RPC erişimi yoksa → ağ hatası; smoke yine de boot loglarını görmeli (RPC sadece bakiye okuma için).

- [ ] **Step 5: `docs/LOCAL_RUN.md` yaz**

```markdown
# Lokal Paper Çalıştırma

## Hızlı başlangıç
```bash
cp .env.local.example .env.local      # düzenleme şart değil; paper için boş secret yeterli
python scripts/run_local_paper.py     # 45s smoke; "[smoke] PASS" görmelisin
```

`run_local_paper.py` ilk çalıştırmada bir burner paper cüzdanı (`wallets.local.json`,
fonlanmamış, sadece simülasyon) oluşturur. Gerçek para/anahtar GEREKMEZ.

## Sürekli paper çalıştırma
```bash
set -a; source .env.local; set +a
KMP_DUPLICATE_LIB_OK=TRUE python -m wallet_manager.orchestrator
```
Durdurmak için Ctrl-C. Mod `robust_paper`; canlı trading kapalı.
```

- [ ] **Step 6: Commit**

```bash
git add .env.local.example scripts/run_local_paper.py docs/LOCAL_RUN.md .gitignore
git commit -m "feat: local paper smoke launcher + run docs"
```

---

### Task 5: Faz 0 kapanış doğrulaması

- [ ] **Step 1: Tam import + targeted test geçişi**

Run:
```bash
KMP_DUPLICATE_LIB_OK=TRUE python -c "import wallet_manager.orchestrator; print('OK')"
KMP_DUPLICATE_LIB_OK=TRUE python -m pytest tests/unit/test_phase5_backtester.py tests/unit/test_config.py -q --no-header 2>&1 | tail -10
```
Expected: `OK`; testler PASS. (Tam suite koşma — HANDOFF kısıtı: makine ısınıyor.)

- [ ] **Step 2: Repo temiz mi**

Run:
```bash
git status --short
git ls-files | grep -iE "task_factories_(yield|algo|short|airdrop)|/alerting.py$|ml_models/archive|_result.txt|\.tar\.gz" || echo "CLEAN — no dead files tracked"
```
Expected: `CLEAN — no dead files tracked`.

- [ ] **Step 3: Push**

```bash
git push origin main
```

---

## Definition of Done (Faz 0)
- Ölü kod (alerting.py + 4 stub) ve disk çöpü gitti; modeller yerinde ve yükleniyor.
- `requirements.txt` kurulu gerçeğe pinli + `requirements.lock.txt` var.
- `python scripts/run_local_paper.py` → `[smoke] PASS` (bot lokalde paper-modda çökmeden bootlanıyor).
- Targeted testler PASS; repo temiz; GitHub'a push'lu.
