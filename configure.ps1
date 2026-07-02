# Interactive settings menu for an installed bot (Windows).
# Usage from the bot folder: .\configure.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "Файл .env не найден — сначала выполните установку (install.ps1)." -ForegroundColor Red
    return
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker не установлен." -ForegroundColor Red
    return
}

# The menu runs inside the bot image (python is guaranteed there), with the
# host .env mounted in. ';' is the COMPOSE_FILE separator on windows.
docker compose run --rm --no-deps -v "${PWD}/.env:/app/.env" bot `
    python tools/configure.py --env /app/.env --sep ";"

if ($LASTEXITCODE -eq 0) {
    Write-Host "Применяю настройки (перезапуск бота)..."
    docker compose up -d
    Write-Host "Готово." -ForegroundColor Green
}
