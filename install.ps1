# One-command installer for aibot-master (Windows, PowerShell).
# Usage:
#   irm https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.ps1 | iex
# Or from a cloned repo: .\install.ps1
$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/MondayDecember/aibot-master.pro.git"
$Dir = "aibot-master"

Write-Host "=== Установка aibot-master ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Ошибка: Docker не установлен. Установите Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor Red
    exit 1
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ошибка: нужен Docker Compose v2 (команда 'docker compose'). Docker Desktop запущен?" -ForegroundColor Red
    exit 1
}

# Clone unless the script is already running inside the repo
if (-not (Test-Path "docker-compose.yml")) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "Ошибка: git не установлен. https://git-scm.com/downloads" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $Dir)) { git clone $RepoUrl $Dir }
    Set-Location $Dir
}

# The bot stores its sqlite db in ./data (bind-mounted into the container)
New-Item -ItemType Directory -Force data | Out-Null
if (Test-Path "bot_data.db") {
    Move-Item bot_data.db data\bot_data.db
    Write-Host "Перенёс bot_data.db со старого пути в data\."
}

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    $token = Read-Host "Введите BOT_TOKEN (получить у @BotFather в Telegram)"
    if (-not $token) { Write-Host "Ошибка: токен пустой." -ForegroundColor Red; exit 1 }
    (Get-Content .env) -replace "^BOT_TOKEN=.*", "BOT_TOKEN=$token" | Set-Content .env
} else {
    Write-Host "Файл .env уже существует — оставляю как есть."
}

# Use Ollama on the host if it's already running, otherwise run it in docker
$ollamaOnHost = $false
try {
    Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
    $ollamaOnHost = $true
    Write-Host "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
} catch {
    Write-Host "Ollama на хосте не найдена — запускаю её в docker-контейнере."
    (Get-Content .env) -replace "^OLLAMA_API_BASE=.*", "OLLAMA_API_BASE=http://ollama:11434/v1" | Set-Content .env
    # COMPOSE_PROFILES in .env makes plain 'docker compose up -d' include ollama
    if (-not (Select-String -Path .env -Pattern "^COMPOSE_PROFILES=" -Quiet)) {
        Add-Content .env "COMPOSE_PROFILES=ollama"
    }
}

Write-Host "Собираю и запускаю контейнеры..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit 1 }

# Pull the models the bot needs
$envMap = @{}
Get-Content .env | Where-Object { $_ -match "^([^#=]+)=(.*)$" } | ForEach-Object {
    $envMap[$Matches[1].Trim()] = $Matches[2].Trim()
}
$textModel = if ($envMap["TEXT_MODEL"]) { $envMap["TEXT_MODEL"] } else { "llama3" }
$visionModel = if ($envMap["VISION_MODEL"]) { $envMap["VISION_MODEL"] } else { "llama3.2-vision" }

if (-not $ollamaOnHost) {
    Write-Host "Скачиваю модели (может занять много времени, они большие)..."
    docker compose exec ollama ollama pull $textModel
    docker compose exec ollama ollama pull $visionModel
} else {
    Write-Host "Убедитесь, что модели скачаны: ollama pull $textModel; ollama pull $visionModel"
}

Write-Host ""
Write-Host "=== Готово! ===" -ForegroundColor Green
Write-Host "Логи бота:      docker compose logs -f bot"
Write-Host "Остановить:     docker compose down"
Write-Host "Обновить:       git pull; docker compose up -d --build"
