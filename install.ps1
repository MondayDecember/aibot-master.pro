# Installer / manager for aibot-master (Windows, PowerShell).
# Usage:
#   irm https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.ps1 | iex
# Or from a cloned repo: .\install.ps1
# When the bot is already installed, this shows a menu (update / reinstall /
# change token / remove) instead of installing again.
#
# NOTE: everything lives inside functions - 'exit' in a script piped to iex
# would close the user's whole PowerShell window, 'return' does not.

function Set-EnvValue {
    param([string]$Key, [string]$Value)
    (Get-Content .env) -replace "^#?\s*$Key=.*", "$Key=$Value" | Set-Content .env
}

function Invoke-Wizard {
    Copy-Item .env.example .env
    $token = Read-Host "Введите BOT_TOKEN (получить у @BotFather; Enter = пропустить и ввести позже)"
    if ($token) {
        Set-EnvValue "BOT_TOKEN" $token
    } else {
        Write-Host "Токен пропущен — установка продолжится, бот запустится и будет ждать токена." -ForegroundColor Yellow
        Write-Host "Ввести позже: .\install.ps1 (пункт «Сменить токен») или .\configure.ps1." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "--- Пара вопросов (Enter = значение по умолчанию, всё можно поменять позже: .\configure.ps1) ---"

    $lang = Read-Host "Язык бота: ru или en [ru]"
    if ($lang -eq "en") { Set-EnvValue "BOT_LANGUAGE" "en" }

    Write-Host "Ваш Telegram ID закроет бота от посторонних и даст вам /stats и оповещения об ошибках."
    Write-Host "Узнать ID: напишите боту @userinfobot. Пусто = бот открыт всем."
    $tgid = Read-Host "Ваш Telegram ID []"
    if ($tgid -match "^\d+$") { Set-EnvValue "ALLOWED_USER_IDS" $tgid }

    $ws = Read-Host "Автопоиск в интернете? Умнее, но ответы примерно вдвое медленнее. y/n [y]"
    if ($ws -eq "n") { Set-EnvValue "AUTO_WEB_SEARCH" "false" }

    $au = Read-Host "Автообновление бота при выходе новых версий (Watchtower)? y/n [n]"
    if ($au -eq "y") { Set-EnvValue "COMPOSE_FILE" "docker-compose.yml;docker-compose.autoupdate.yml" }

    # Pick models that actually fit this machine
    $memGb = 0
    try { $memGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch {}
    $gpuNote = ""
    try {
        if ((Get-CimInstance Win32_VideoController).Name -match "NVIDIA") {
            $gpuNote = ", есть видеокарта NVIDIA (модели будут работать быстро)"
        }
    } catch {}

    $rec = if ($memGb -lt 8) { "1" } elseif ($memGb -lt 16) { "2" } elseif ($memGb -lt 32) { "3" } else { "4" }
    Write-Host ""
    Write-Host "Ваша система: ОЗУ $memGb ГБ$gpuNote."
    Write-Host "Текстовая модель (мозг бота):"
    Write-Host "  1) llama3.2:3b — лёгкая и быстрая (~4 ГБ ОЗУ)"
    Write-Host "  2) llama3 (8B) — баланс качества и скорости (~8 ГБ ОЗУ)"
    Write-Host "  3) qwen2.5:14b — заметно умнее (~12–16 ГБ ОЗУ)"
    Write-Host "  4) qwen2.5:32b — максимум качества (~24+ ГБ ОЗУ)"
    $modelChoice = Read-Host "Выбор [$rec — рекомендуется для вашей системы]"
    if (-not $modelChoice) { $modelChoice = $rec }
    $textModelMap = @{ "1" = "llama3.2:3b"; "3" = "qwen2.5:14b"; "4" = "qwen2.5:32b" }
    if ($textModelMap.ContainsKey($modelChoice)) { Set-EnvValue "TEXT_MODEL" $textModelMap[$modelChoice] }

    $visionRec = if ($memGb -lt 8) { "3" } else { "2" }
    Write-Host ""
    Write-Host "Модель для анализа фото (vision) - бот распознаёт, что на картинке, а не рисует их:"
    Write-Host "  1) llama3.2-vision (11B) - от Meta, надёжный универсальный выбор (~10 ГБ ОЗУ)"
    Write-Host "  2) qwen2.5vl:7b - легче и часто точнее на бенчмарках (~6 ГБ ОЗУ)"
    Write-Host "  3) moondream - совсем лёгкая и быстрая, слабее качеством - для слабого железа (~3 ГБ ОЗУ)"
    $visionChoice = Read-Host "Выбор [$visionRec — рекомендуется для вашей системы]"
    if (-not $visionChoice) { $visionChoice = $visionRec }
    $visionModelMap = @{ "1" = "llama3.2-vision"; "2" = "qwen2.5vl:7b"; "3" = "moondream" }
    $chosenVision = if ($visionModelMap.ContainsKey($visionChoice)) { $visionModelMap[$visionChoice] } else { "qwen2.5vl:7b" }
    Set-EnvValue "VISION_MODEL" $chosenVision
}

function Start-Containers {
    if (Select-String -Path .env -Pattern "^COMPOSE_FILE=" -Quiet) {
        Write-Host "Скачиваю готовый образ и запускаю контейнеры..."
        docker compose up -d
    } else {
        Write-Host "Собираю и запускаю контейнеры..."
        docker compose up -d --build
    }
    return $LASTEXITCODE -eq 0
}

function Initialize-OllamaAndLaunch {
    $ollamaOnHost = $false
    $skipDockerOllama = $false
    try {
        Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
        $ollamaOnHost = $true
        Write-Host "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
    } catch {
        Write-Host ""
        Write-Host "Ollama на хосте не найдена (либо ещё не запустилась)." -ForegroundColor Yellow
        $runInDocker = Read-Host "Запустить Ollama в docker-контейнере и скачать в неё модели (несколько ГБ)? y/n [y]"
        if ($runInDocker -eq "n") {
            Write-Host "Пропускаю. Установите Ollama сами (https://ollama.com) или укажите OLLAMA_API_BASE в .env." -ForegroundColor Yellow
            $skipDockerOllama = $true
        } else {
            $apiBase = (Get-Content .env | Select-String "^OLLAMA_API_BASE=").Line
            if ($apiBase -match "host\.docker\.internal|localhost|127\.0\.0\.1" ) {
                Set-EnvValue "OLLAMA_API_BASE" "http://ollama:11434/v1"
            } elseif ($apiBase -and $apiBase -notmatch "//ollama:") {
                Write-Host "В .env задан свой OLLAMA_API_BASE — оставляю его как есть." -ForegroundColor Yellow
            }
            if (-not (Select-String -Path .env -Pattern "^COMPOSE_PROFILES=" -Quiet)) {
                Add-Content .env "COMPOSE_PROFILES=ollama"
            }
        }
    }

    if (-not (Start-Containers)) {
        Write-Host "Ошибка: docker compose up завершился неудачно, см. вывод выше." -ForegroundColor Red
        return
    }

    $envMap = @{}
    Get-Content .env | Where-Object { $_ -match "^([^#=]+)=(.*)$" } | ForEach-Object {
        $envMap[$Matches[1].Trim()] = $Matches[2].Trim()
    }
    $textModel = if ($envMap["TEXT_MODEL"]) { $envMap["TEXT_MODEL"] } else { "llama3" }
    $visionModel = if ($envMap["VISION_MODEL"]) { $envMap["VISION_MODEL"] } else { "llama3.2-vision" }

    if ($skipDockerOllama) {
        Write-Host "Модели не скачаны - настройте Ollama и выполните: ollama pull $textModel; ollama pull $visionModel" -ForegroundColor Yellow
    } elseif (-not $ollamaOnHost) {
        Write-Host "Жду запуска Ollama в контейнере..."
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            docker compose exec ollama ollama list *> $null
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
            Start-Sleep -Seconds 2
        }
        if (-not $ready) {
            Write-Host "Ollama в контейнере не отвечает. Скачайте модели вручную: docker compose exec ollama ollama pull $textModel" -ForegroundColor Red
            return
        }
        Write-Host "Скачиваю модели (может занять много времени, они большие)..."
        docker compose exec ollama ollama pull $textModel
        docker compose exec ollama ollama pull $visionModel
    } else {
        Write-Host "Убедитесь, что модели скачаны: ollama pull $textModel; ollama pull $visionModel"
    }

    Write-Host ""
    Write-Host "=== Готово! ===" -ForegroundColor Green
    Write-Host "Меню управления:  .\install.ps1"
    Write-Host "Логи бота:        docker compose logs -f bot"
    Write-Host "Остановить:       docker compose down"
}

# ---- menu actions -------------------------------------------------------
function Invoke-Update {
    if (Test-Path .git) {
        Write-Host "Забираю обновления из репозитория..."
        git pull --ff-only
        if ($LASTEXITCODE -ne 0) { Write-Host "git pull не удался — продолжаю с текущим кодом." -ForegroundColor Yellow }
    }
    Start-Containers | Out-Null
    Write-Host "Обновление завершено." -ForegroundColor Green
}

function Invoke-Reinstall {
    Write-Host "Пересобираю и пересоздаю контейнеры (настройки и данные сохраняются)..."
    if (Select-String -Path .env -Pattern "^COMPOSE_FILE=" -Quiet) {
        docker compose up -d --force-recreate
    } else {
        docker compose up -d --build --force-recreate
    }
    Write-Host "Переустановка завершена." -ForegroundColor Green
}

function Invoke-ChangeToken {
    $token = Read-Host "Введите новый BOT_TOKEN (Enter = отмена)"
    if (-not $token) { Write-Host "Отменено."; return }
    Set-EnvValue "BOT_TOKEN" $token
    Write-Host "Токен обновлён, перезапускаю бота..."
    docker compose up -d
    Write-Host "Готово." -ForegroundColor Green
}

function Invoke-Remove {
    $confirm = Read-Host "Остановить и удалить контейнеры? История и настройки пока сохранятся. y/n [n]"
    if ($confirm -ne "y") { Write-Host "Отменено."; return }
    docker compose down
    $purge = Read-Host "Удалить ТАКЖЕ все данные — историю, настройки (.env), бэкапы? БЕЗВОЗВРАТНО. y/n [n]"
    if ($purge -eq "y") {
        docker compose down -v *> $null
        Remove-Item -Recurse -Force data, .env -ErrorAction SilentlyContinue
        Write-Host "Данные удалены. Папку можете удалить вручную." -ForegroundColor Green
    } else {
        Write-Host "Контейнеры остановлены. Данные сохранены. Запустить снова: .\install.ps1"
    }
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "=== aibot-master — бот уже установлен ===" -ForegroundColor Cyan
        Write-Host "  1) Обновить (забрать новую версию и перезапустить)"
        Write-Host "  2) Переустановить (пересобрать контейнеры, настройки сохранить)"
        Write-Host "  3) Сменить токен бота Telegram"
        Write-Host "  4) Изменить настройки (язык, доступ, модели...)"
        Write-Host "  5) Удалить бота"
        Write-Host "  0) Выход"
        $choice = Read-Host "Выбор"
        switch ($choice) {
            "1" { Invoke-Update }
            "2" { Invoke-Reinstall }
            "3" { Invoke-ChangeToken }
            "4" { & .\configure.ps1 }
            "5" { Invoke-Remove; return }
            "0" { return }
            default { Write-Host "Введите число от 0 до 5." }
        }
    }
}

function Install-Aibot {
    $ErrorActionPreference = "Stop"
    $RepoUrl = "https://github.com/MondayDecember/aibot-master.pro.git"
    $Dir = "aibot-master"

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Ошибка: Docker не установлен. Установите Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor Red
        return
    }
    docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Ошибка: нужен Docker Compose v2 (команда 'docker compose'). Docker Desktop запущен?" -ForegroundColor Red
        return
    }

    if (-not (Test-Path "docker-compose.yml")) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "Ошибка: git не установлен. https://git-scm.com/downloads" -ForegroundColor Red
            return
        }
        if (-not (Test-Path $Dir)) { git clone $RepoUrl $Dir }
        Set-Location $Dir
    }

    New-Item -ItemType Directory -Force data | Out-Null
    if (Test-Path "bot_data.db") {
        Move-Item bot_data.db data\bot_data.db
        Write-Host "Перенёс bot_data.db со старого пути в data\."
    }

    if (Test-Path ".env") {
        Show-Menu
    } else {
        Write-Host "=== Установка aibot-master ===" -ForegroundColor Cyan
        Invoke-Wizard
        Initialize-OllamaAndLaunch
    }
}

Install-Aibot
