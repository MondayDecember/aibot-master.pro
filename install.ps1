# One-command installer for aibot-master (Windows, PowerShell).
# Usage:
#   irm https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.ps1 | iex
# Or from a cloned repo: .\install.ps1
#
# NOTE: everything lives inside a function - 'exit' in a script piped to iex
# would close the user's whole PowerShell window, 'return' does not.
function Install-Aibot {
    $ErrorActionPreference = "Stop"

    $RepoUrl = "https://github.com/MondayDecember/aibot-master.pro.git"
    $Dir = "aibot-master"

    Write-Host "=== Установка aibot-master ===" -ForegroundColor Cyan

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Ошибка: Docker не установлен. Установите Docker Desktop: https://docs.docker.com/desktop/setup/install/windows-install/" -ForegroundColor Red
        return
    }
    docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Ошибка: нужен Docker Compose v2 (команда 'docker compose'). Docker Desktop запущен?" -ForegroundColor Red
        return
    }

    # Clone unless the script is already running inside the repo
    if (-not (Test-Path "docker-compose.yml")) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "Ошибка: git не установлен. https://git-scm.com/downloads" -ForegroundColor Red
            return
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
        $token = Read-Host "Введите BOT_TOKEN (получить у @BotFather; Enter = пропустить и ввести позже)"
        if ($token) {
            (Get-Content .env) -replace "^BOT_TOKEN=.*", "BOT_TOKEN=$token" | Set-Content .env
        } else {
            Write-Host "Токен пропущен — установка продолжится, бот запустится и будет ждать токена." -ForegroundColor Yellow
            Write-Host "Ввести позже: .\configure.ps1 (пункт 1) или впишите BOT_TOKEN в .env." -ForegroundColor Yellow
        }

        Write-Host ""
        Write-Host "--- Пара вопросов (Enter = значение по умолчанию, всё можно поменять позже: .\configure.ps1) ---"

        $lang = Read-Host "Язык бота: ru или en [ru]"
        if ($lang -eq "en") {
            (Get-Content .env) -replace "^BOT_LANGUAGE=.*", "BOT_LANGUAGE=en" | Set-Content .env
        }

        Write-Host "Ваш Telegram ID закроет бота от посторонних и даст вам /stats и оповещения об ошибках."
        Write-Host "Узнать ID: напишите боту @userinfobot. Пусто = бот открыт всем."
        $tgid = Read-Host "Ваш Telegram ID []"
        if ($tgid -match "^\d+$") {
            (Get-Content .env) -replace "^# ALLOWED_USER_IDS=.*", "ALLOWED_USER_IDS=$tgid" | Set-Content .env
        }

        $ws = Read-Host "Автопоиск в интернете? Умнее, но ответы примерно вдвое медленнее. y/n [y]"
        if ($ws -eq "n") {
            (Get-Content .env) -replace "^AUTO_WEB_SEARCH=.*", "AUTO_WEB_SEARCH=false" | Set-Content .env
        }

        $au = Read-Host "Автообновление бота при выходе новых версий (Watchtower)? y/n [n]"
        if ($au -eq "y") {
            (Get-Content .env) -replace "^# COMPOSE_FILE=.*", "COMPOSE_FILE=docker-compose.yml;docker-compose.autoupdate.yml" | Set-Content .env
        }

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
        if ($textModelMap.ContainsKey($modelChoice)) {
            (Get-Content .env) -replace "^TEXT_MODEL=.*", "TEXT_MODEL=$($textModelMap[$modelChoice])" | Set-Content .env
        }

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
        (Get-Content .env) -replace "^VISION_MODEL=.*", "VISION_MODEL=$chosenVision" | Set-Content .env
    } else {
        Write-Host "Файл .env уже существует — оставляю как есть (настройки: .\configure.ps1)."
    }

    # Use Ollama on the host if it's already running, otherwise run it in docker.
    # Only touch OLLAMA_API_BASE while it still points to a default location -
    # a custom value (e.g. a remote Ollama server) must be left alone.
    $ollamaOnHost = $false
    $skipDockerOllama = $false
    try {
        Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3 | Out-Null
        $ollamaOnHost = $true
        Write-Host "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
    } catch {
        Write-Host ""
        Write-Host "Ollama на хосте не найдена (либо ещё не запустилась - проверьте, что она точно не работает)." -ForegroundColor Yellow
        $runInDocker = Read-Host "Запустить Ollama в отдельном docker-контейнере и скачать в неё модели (несколько ГБ, займёт время и место на диске)? y/n [y]"
        if ($runInDocker -eq "n") {
            Write-Host "Пропускаю. Установите Ollama сами (https://ollama.com) или укажите свой OLLAMA_API_BASE в .env, затем: docker compose up -d" -ForegroundColor Yellow
            $skipDockerOllama = $true
        } else {
            $apiBase = (Get-Content .env | Select-String "^OLLAMA_API_BASE=").Line
            if ($apiBase -match "host\.docker\.internal|localhost|127\.0\.0\.1" ) {
                (Get-Content .env) -replace "^OLLAMA_API_BASE=.*", "OLLAMA_API_BASE=http://ollama:11434/v1" | Set-Content .env
            } elseif ($apiBase -and $apiBase -notmatch "//ollama:") {
                Write-Host "В .env задан свой OLLAMA_API_BASE — оставляю его как есть." -ForegroundColor Yellow
            }
            # COMPOSE_PROFILES in .env makes plain 'docker compose up -d' include ollama
            if (-not (Select-String -Path .env -Pattern "^COMPOSE_PROFILES=" -Quiet)) {
                Add-Content .env "COMPOSE_PROFILES=ollama"
            }
        }
    }

    if (Select-String -Path .env -Pattern "^COMPOSE_FILE=" -Quiet) {
        # Auto-update mode: run from the prebuilt registry image, don't build
        Write-Host "Скачиваю готовый образ и запускаю контейнеры..."
        docker compose up -d
    } else {
        Write-Host "Собираю и запускаю контейнеры..."
        docker compose up -d --build
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Ошибка: docker compose up завершился неудачно, см. вывод выше." -ForegroundColor Red
        return
    }

    # Pull the models the bot needs
    $envMap = @{}
    Get-Content .env | Where-Object { $_ -match "^([^#=]+)=(.*)$" } | ForEach-Object {
        $envMap[$Matches[1].Trim()] = $Matches[2].Trim()
    }
    $textModel = if ($envMap["TEXT_MODEL"]) { $envMap["TEXT_MODEL"] } else { "llama3" }
    $visionModel = if ($envMap["VISION_MODEL"]) { $envMap["VISION_MODEL"] } else { "llama3.2-vision" }

    if ($skipDockerOllama) {
        Write-Host "Модели не скачаны - настройте свою Ollama и выполните: ollama pull $textModel; ollama pull $visionModel" -ForegroundColor Yellow
    } elseif (-not $ollamaOnHost) {
        # Wait until the ollama server inside the container answers
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
    Write-Host "Логи бота:      docker compose logs -f bot"
    Write-Host "Остановить:     docker compose down"
    Write-Host "Обновить:       git pull; docker compose up -d --build"
}

Install-Aibot
