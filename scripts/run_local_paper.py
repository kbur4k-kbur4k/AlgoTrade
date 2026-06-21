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
