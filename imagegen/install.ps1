# One-time setup for the local image-generation service (Windows only).
# Usage: .\install.ps1
#
# Why this isn't a docker-compose service: on this box (and Windows Docker
# Desktop generally), neither DirectML nor CUDA GPU passthrough into
# containers is reliably available (`docker run --gpus all ...` fails with
# "WSL environment detected but no adapters were found" even though the
# same GPU works fine for natively-running apps). Same reason Ollama itself
# runs natively here instead of in docker - see the main README.
function Set-BackendEnv {
    # Persist the chosen backend into imagegen/.env so run.ps1 uses it. Adds
    # or replaces the IMAGEGEN_BACKEND line without touching anything else.
    param([string]$Backend)
    if (-not (Test-Path .env)) {
        if (Test-Path .env.example) { Copy-Item .env.example .env } else { New-Item -ItemType File .env | Out-Null }
    }
    $lines = Get-Content .env
    if ($lines -match "^\s*IMAGEGEN_BACKEND=") {
        $lines = $lines -replace "^\s*IMAGEGEN_BACKEND=.*", "IMAGEGEN_BACKEND=$Backend"
        $lines | Set-Content .env
    } else {
        Add-Content .env "IMAGEGEN_BACKEND=$Backend"
    }
    Write-Host "Записал IMAGEGEN_BACKEND=$Backend в imagegen\.env"
}

function Set-ModelEnv {
    # Persist the chosen model + its recommended steps/guidance into
    # imagegen/.env. Turbo models want steps=1, guidance=0; the full SDXL
    # base model needs many more steps and non-zero guidance to look right -
    # using turbo settings on it would produce noise.
    param([string]$Model, [string]$Steps, [string]$Guidance)
    if (-not (Test-Path .env)) {
        if (Test-Path .env.example) { Copy-Item .env.example .env } else { New-Item -ItemType File .env | Out-Null }
    }
    $lines = Get-Content .env
    foreach ($pair in @(@("IMAGEGEN_MODEL", $Model), @("IMAGEGEN_STEPS", $Steps), @("IMAGEGEN_GUIDANCE_SCALE", $Guidance))) {
        $key, $val = $pair
        if ($lines -match "^\s*$key=") {
            $lines = $lines -replace "^\s*$key=.*", "$key=$val"
        } else {
            $lines += "$key=$val"
        }
    }
    $lines | Set-Content .env
    Write-Host "Записал IMAGEGEN_MODEL=$Model (шагов: $Steps, guidance: $Guidance) в imagegen\.env"
}

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

    # Detect an NVIDIA GPU and offer the fast native CUDA path; otherwise the
    # portable DirectML path (AMD / Intel / older NVIDIA on Windows).
    $hasNvidia = $false
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { $hasNvidia = $true }

    if ($hasNvidia) {
        Write-Host "Обнаружена видеокарта NVIDIA." -ForegroundColor Green
        Write-Host "  1) CUDA - родной ускоренный путь для NVIDIA (рекомендуется, быстрее)"
        Write-Host "  2) DirectML - универсальный путь (медленнее на NVIDIA)"
        $backend = Read-Host "Выбор [1]"
        if (-not $backend) { $backend = "1" }
    } else {
        Write-Host "Видеокарта NVIDIA не найдена - ставлю DirectML (AMD / Intel / CPU)."
        $backend = "2"
    }

    if ($backend -eq "1") {
        # CUDA 12.8 wheels cover the RTX 50-series (Blackwell) and older 40/30
        # series alike. Change cu128 to match an older CUDA if needed.
        $cuda = Read-Host "Версия CUDA-колёс: cu128 (50-й ряд/новые), cu124 (40/30) [cu128]"
        if (-not $cuda) { $cuda = "cu128" }
        Write-Host "Ставлю torch (CUDA $cuda) - это несколько ГБ, займёт время..."
        .\venv\Scripts\python.exe -m pip install torch --index-url "https://download.pytorch.org/whl/$cuda"
        .\venv\Scripts\python.exe -m pip install -q -r requirements-cuda.txt
        Set-BackendEnv "cuda"
    } else {
        Write-Host "Ставлю зависимости DirectML (torch скачается - несколько сотен МБ)..."
        .\venv\Scripts\python.exe -m pip install -q -r requirements.txt
        Set-BackendEnv "directml"
    }

    Write-Host ""
    Write-Host "Какую модель генерации картинок использовать?" -ForegroundColor Cyan
    Write-Host "  1) SD-Turbo - лёгкая (~1 ГБ), 1 шаг, пара секунд на картинку"
    Write-Host "  2) SDXL-Turbo - заметно качественнее, всё ещё быстрая (~7 ГБ, 1-4 шага)"
    Write-Host "  3) SDXL base - максимальное качество (~7 ГБ), но медленнее (20-30 шагов)"
    $modelChoice = Read-Host "Выбор [1]"
    switch ($modelChoice) {
        "2" { Set-ModelEnv "stabilityai/sdxl-turbo" "1" "0.0" }
        "3" { Set-ModelEnv "stabilityai/stable-diffusion-xl-base-1.0" "30" "7.0" }
        default { Set-ModelEnv "stabilityai/sd-turbo" "1" "0.0" }
    }

    Write-Host ""
    Write-Host "=== Готово ===" -ForegroundColor Green
    Write-Host "Запуск:  .\run.ps1"
    Write-Host "Модель скачается при первом запросе картинки, не при старте сервиса."
    Write-Host ""
    Write-Host "Чтобы сервис поднимался вместе с Windows, добавьте .\run.ps1 в Планировщик заданий"
    Write-Host "(триггер 'При входе в систему'), как это обычно делают с Ollama."
}

Install-ImageGen
