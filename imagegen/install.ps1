# One-time setup for the local image-generation service (Windows only).
# Usage: .\install.ps1
#
# Why this isn't a docker-compose service: on this box (and Windows Docker
# Desktop generally), neither DirectML nor CUDA GPU passthrough into
# containers is reliably available (`docker run --gpus all ...` fails with
# "WSL environment detected but no adapters were found" even though the
# same GPU works fine for natively-running apps). Same reason Ollama itself
# runs natively here instead of in docker - see the main README.
function Install-ImageGen {
    $ErrorActionPreference = "Stop"

    Write-Host "=== Настройка сервиса генерации картинок ===" -ForegroundColor Cyan

    # torch-directml has no wheel for Python 3.13+ yet - need 3.9-3.12.
    $pyCmd = $null
    foreach ($v in @("3.11", "3.12", "3.10", "3.9")) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            py "-$v" --version *> $null
            if ($LASTEXITCODE -eq 0) { $pyCmd = "-$v"; break }
        }
    }
    if (-not $pyCmd) {
        Write-Host "Ошибка: нужен Python 3.9-3.12 (torch-directml пока не поддерживает 3.13+)." -ForegroundColor Red
        Write-Host "Установите, например, Python 3.11: https://www.python.org/downloads/"
        return
    }
    Write-Host "Использую python $pyCmd"

    if (-not (Test-Path venv)) {
        py $pyCmd -m venv venv
    }
    .\venv\Scripts\python.exe -m pip install -q --upgrade pip
    Write-Host "Ставлю зависимости (torch скачается - несколько сотен МБ)..."
    .\venv\Scripts\python.exe -m pip install -q -r requirements.txt

    Write-Host ""
    Write-Host "=== Готово ===" -ForegroundColor Green
    Write-Host "Запуск:  .\run.ps1"
    Write-Host "Модель (~1 ГБ) скачается при первом запросе картинки, не при старте сервиса."
    Write-Host ""
    Write-Host "Чтобы сервис поднимался вместе с Windows, добавьте .\run.ps1 в Планировщик заданий"
    Write-Host "(триггер 'При входе в систему'), как это обычно делают с Ollama."
}

Install-ImageGen
