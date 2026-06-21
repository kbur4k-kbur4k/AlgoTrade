"""
scripts/retrain_schedule.py

Weekly Model Retraining Scheduler — Phase 11

Wraps train_models.py with safety checks and reporting.
Run this script weekly via cron or manually when LearningOS flags
retraining_recommended=True.

Usage:
    python scripts/retrain_schedule.py              # check age + retrain if needed
    python scripts/retrain_schedule.py --force      # retrain unconditionally
    python scripts/retrain_schedule.py --check-only # print status, do not train

Azure cron (add to crontab on the VM — runs inside the container):
    0 3 * * 0  cd /app && python scripts/retrain_schedule.py >> /app/data/retrain.log 2>&1

Exit codes:
    0  — training ran and succeeded (or skipped because models are fresh)
    1  — training ran and failed
    2  — insufficient data (run historical_data_pipeline first)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

TRAINING_REPORT = _ROOT / "wallet_manager" / "ml_models" / "training_report.json"
TRAIN_SCRIPT = _ROOT / "scripts" / "train_models.py"
RETRAIN_INTERVAL_DAYS = 7.0


def _model_age_days() -> float:
    """Return model age in days, or 999 if report not found."""
    if not TRAINING_REPORT.exists():
        return 999.0
    try:
        data = json.loads(TRAINING_REPORT.read_text(encoding="utf-8"))
        ts_str = data.get("trained_at") or data.get("generated_at", "")
        if not ts_str:
            return 999.0
        trained_at = datetime.fromisoformat(ts_str)
        if trained_at.tzinfo is None:
            trained_at = trained_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - trained_at).total_seconds() / 86400.0
    except Exception as exc:
        print(f"[retrain_schedule] Could not read training_report.json: {exc}")
        return 999.0


def _print_status(age_days: float) -> None:
    print(f"[retrain_schedule] Model age : {age_days:.1f} days")
    print(f"[retrain_schedule] Threshold : {RETRAIN_INTERVAL_DAYS:.0f} days")
    if TRAINING_REPORT.exists():
        try:
            data = json.loads(TRAINING_REPORT.read_text(encoding="utf-8"))
            models = data.get("models", {})
            for name, m in models.items():
                accepted = m.get("accepted", False)
                sharpe = m.get("oos_sharpe", "n/a")
                print(f"[retrain_schedule]   {name:<12} accepted={accepted}  oos_sharpe={sharpe}")
        except Exception:
            pass


def _run_training(force: bool = False) -> int:
    """Invoke train_models.py as a subprocess. Returns exit code."""
    cmd = [sys.executable, str(TRAIN_SCRIPT)]
    if force:
        cmd.append("--force")
    print(f"[retrain_schedule] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(_ROOT))
    return result.returncode


async def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly model retraining scheduler")
    parser.add_argument("--force", action="store_true", help="Retrain unconditionally")
    parser.add_argument("--check-only", action="store_true", help="Print status only")
    args = parser.parse_args()

    age_days = _model_age_days()
    _print_status(age_days)

    if args.check_only:
        needs = age_days >= RETRAIN_INTERVAL_DAYS
        print(f"[retrain_schedule] Retraining needed: {needs}")
        return 0

    if not args.force and age_days < RETRAIN_INTERVAL_DAYS:
        print(
            f"[retrain_schedule] Models are {age_days:.1f} days old — "
            f"below {RETRAIN_INTERVAL_DAYS:.0f}d threshold. Skipping."
        )
        return 0

    print(
        f"[retrain_schedule] {'Forced retraining' if args.force else f'Models are {age_days:.1f}d old'}. "
        "Starting training pipeline..."
    )

    exit_code = _run_training(force=args.force)

    if exit_code == 0:
        new_age = _model_age_days()
        print(f"[retrain_schedule] Training complete. New model age: {new_age:.1f} days.")
        return 0
    elif exit_code == 2:
        print(
            "[retrain_schedule] Insufficient training data. "
            "Run: python scripts/data/historical_data_pipeline.py --fetch"
        )
        return 2
    else:
        print(f"[retrain_schedule] Training failed with exit code {exit_code}.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
