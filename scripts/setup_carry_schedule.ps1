# setup_carry_schedule.ps1 — OPERATÖR çalıştırır (otomatik kurulmadı, izin gerekli).
#
# Carry forward-tracker'ı (scripts/carry_tracker.py) her 8 saatte bir koşan, BEDAVA
# (yerel python, API harcaması YOK) bir Windows zamanlanmış görev kurar.
# CLAUDE.md süreklilik düzeneği — gerçek para/canlı trade ASLA tetiklemez, sadece
# paper funding gözlemi kaydeder.
#
# KUR:    powershell -ExecutionPolicy Bypass -File scripts\setup_carry_schedule.ps1
# KALDIR: schtasks /Delete /TN "WalletBot_CarryTracker" /F
# DURUM:  schtasks /Query /TN "WalletBot_CarryTracker" /FO LIST
# LOG:    carry_tracker.log (proje kökünde)

$proj = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python).Source
$action = "cmd /c cd /d `"$proj`" && `"$py`" -m scripts.carry_tracker >> `"$proj\carry_tracker.log`" 2>&1"

schtasks /Create /TN "WalletBot_CarryTracker" /TR $action /SC HOURLY /MO 8 /F
Write-Host "Kuruldu. Kaldirmak icin: schtasks /Delete /TN WalletBot_CarryTracker /F"
