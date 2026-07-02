# setup_carry_schedule.ps1 — OPERATÖR çalıştırır (otomatik kurulmadı, izin gerekli).
#
# Her 8 saatte bir, BEDAVA (yerel python, API harcaması YOK) iki kayıt koşar:
#   1. scripts/carry_tracker.py   — carry nöbeti + T1 tetik kontrolü
#   2. scripts/market_recorder.py — veri-hendeği teybi (orderbook/OI/funding; ROADMAP T5)
# CLAUDE.md süreklilik düzeneği — gerçek para/canlı trade ASLA tetiklemez; sadece
# paper gözlem kaydeder. Makine kapalıyken kayıt atlanır (best-effort, kabul edilen bedel).
#
# KUR:    powershell -ExecutionPolicy Bypass -File scripts\setup_carry_schedule.ps1
# KALDIR: schtasks /Delete /TN "WalletBot_CarryTracker" /F
# DURUM:  schtasks /Query /TN "WalletBot_CarryTracker" /FO LIST
# LOG:    carry_tracker.log (proje kökünde)

$proj = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python).Source
# NOT: iki koşu '&' ile bağlı (koşulsuz) — nöbet düşerse teyp yine de kaydetsin.
$action = "cmd /c cd /d `"$proj`" & `"$py`" -m scripts.carry_tracker >> `"$proj\carry_tracker.log`" 2>&1 & `"$py`" -m scripts.market_recorder >> `"$proj\carry_tracker.log`" 2>&1"

schtasks /Create /TN "WalletBot_CarryTracker" /TR $action /SC HOURLY /MO 8 /F
Write-Host "Kuruldu: 8 saatte bir carry nobeti + veri teybi. Kaldirmak icin: schtasks /Delete /TN WalletBot_CarryTracker /F"
