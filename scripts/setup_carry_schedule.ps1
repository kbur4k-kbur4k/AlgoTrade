# setup_carry_schedule.ps1 — OPERATÖR çalıştırır (otomatik kurulmadı, izin gerekli).
#
# Her 8 saatte bir, BEDAVA (yerel python, API harcaması YOK) iki kayıt koşar:
#   1. scripts/carry_tracker.py   — carry nöbeti + T1 tetik kontrolü
#   2. scripts/market_recorder.py — veri-hendeği teybi (orderbook/OI/funding; ROADMAP T5)
# CLAUDE.md süreklilik düzeneği — gerçek para/canlı trade ASLA tetiklemez; sadece
# paper gözlem kaydeder. Makine kapalıyken kayıt atlanır (best-effort, kabul edilen bedel).
#
# NOT: schtasks /TR 261 karakterle sınırlı → komutlar scripts\run_watch.cmd'ye
# yazılır, görev sadece o kısa yolu çağırır.
#
# KUR:    powershell -ExecutionPolicy Bypass -File scripts\setup_carry_schedule.ps1
# KALDIR: schtasks /Delete /TN "WalletBot_CarryTracker" /F
# DURUM:  schtasks /Query /TN "WalletBot_CarryTracker" /FO LIST
# LOG:    carry_tracker.log (proje kökünde)

$proj = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python).Source
$cmd = Join-Path $proj "scripts\run_watch.cmd"

# Görevin çağıracağı kısa batch dosyasını üret (mutlak python yolu gömülü).
@"
@echo off
cd /d "$proj"
"$py" -m scripts.carry_tracker >> carry_tracker.log 2>&1
"$py" -m scripts.market_recorder >> carry_tracker.log 2>&1
"@ | Set-Content -Path $cmd -Encoding ascii

schtasks /Create /TN "WalletBot_CarryTracker" /TR "`"$cmd`"" /SC HOURLY /MO 8 /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "KURULDU: 8 saatte bir carry nobeti + veri teybi."
    Write-Host "Test: schtasks /Run /TN WalletBot_CarryTracker"
} else {
    Write-Host "HATA: gorev kurulamadi (exit $LASTEXITCODE). Yukaridaki mesaja bak."
}
