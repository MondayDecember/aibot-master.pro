#!/usr/bin/env bash
# Installer / manager for aibot-master (Linux/macOS).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.sh | bash
# Or from a cloned repo: bash install.sh
# When the bot is already installed, this shows a menu (update / reinstall /
# change token / remove) instead of installing again.
set -uo pipefail

REPO_URL="https://github.com/MondayDecember/aibot-master.pro.git"
DIR="aibot-master"

# portable in-place sed (GNU and BSD/macOS)
sed_i() { sed -i.bak "$1" "$2" && rm -f "$2.bak"; }

# Rough download sizes (GB) for the models offered below - used to warn
# before recommending or pulling one that won't fit on the models drive.
# A function (not an associative array) for bash 3.2 compat (macOS default).
model_size_gb() {
    case "$1" in
        "llama3.2:3b") echo 2 ;;
        "llama3") echo 5 ;;
        "qwen2.5:14b") echo 9 ;;
        "qwen2.5:32b") echo 20 ;;
        "llama3.2-vision") echo 8 ;;
        "qwen2.5vl:7b") echo 6 ;;
        "moondream") echo 2 ;;
        *) echo "" ;;
    esac
}

ollama_models_path() { echo "${OLLAMA_MODELS:-$HOME/.ollama/models}"; }

free_space_gb() {
    # $1 = path (may not exist yet - walk up to the nearest existing dir)
    local p="$1"
    while [ ! -d "$p" ] && [ "$p" != "/" ]; do p=$(dirname "$p"); done
    df -Pk "$p" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1024/1024}'
}

require_docker() {
    command -v docker >/dev/null 2>&1 || {
        echo "Ошибка: Docker не установлен. См. https://docs.docker.com/engine/install/"
        exit 1
    }
    docker compose version >/dev/null 2>&1 || {
        echo "Ошибка: нужен Docker Compose v2 (команда 'docker compose')."
        exit 1
    }
}

# ---- .env creation wizard (fresh install only) --------------------------
run_wizard() {
    cp .env.example .env
    printf "Введите BOT_TOKEN (получить у @BotFather; Enter = пропустить и ввести позже): "
    read -r token </dev/tty
    if [ -n "$token" ]; then
        sed_i "s|^BOT_TOKEN=.*|BOT_TOKEN=${token}|" .env
    else
        echo "Токен пропущен — установка продолжится, бот запустится и будет ждать токена."
        echo "Ввести позже: bash install.sh (пункт «Сменить токен») или bash configure.sh."
    fi

    echo ""
    echo "--- Пара вопросов (Enter = значение по умолчанию, всё можно поменять позже: bash configure.sh) ---"

    printf "Язык бота: ru или en [ru]: "
    read -r lang </dev/tty
    [ "${lang:-ru}" = "en" ] && sed_i "s|^BOT_LANGUAGE=.*|BOT_LANGUAGE=en|" .env

    echo "Ваш Telegram ID закроет бота от посторонних и даст вам /stats и оповещения об ошибках."
    echo "Узнать ID: напишите боту @userinfobot. Пусто = бот открыт всем."
    printf "Ваш Telegram ID []: "
    read -r tgid </dev/tty
    if echo "$tgid" | grep -qE '^[0-9]+$'; then
        sed_i "s|^# ALLOWED_USER_IDS=.*|ALLOWED_USER_IDS=${tgid}|" .env
    fi

    printf "Автопоиск в интернете? Умнее, но ответы примерно вдвое медленнее. y/n [y]: "
    read -r ws </dev/tty
    [ "${ws:-y}" = "n" ] && sed_i "s|^AUTO_WEB_SEARCH=.*|AUTO_WEB_SEARCH=false|" .env

    printf "Автообновление бота при выходе новых версий (Watchtower)? y/n [n]: "
    read -r au </dev/tty
    if [ "${au:-n}" = "y" ]; then
        sed_i "s|^# COMPOSE_FILE=.*|COMPOSE_FILE=docker-compose.yml:docker-compose.autoupdate.yml|" .env
    fi

    # Where Ollama stores models - ask before recommending anything, since
    # the recommendation itself depends on how much room is there.
    echo ""
    models_path=$(ollama_models_path)
    free_gb=$(free_space_gb "$models_path")
    if [ -n "$free_gb" ]; then free_note="свободно ${free_gb} ГБ"; else free_note="папка ещё не создана"; fi
    echo "Модели Ollama хранятся здесь: ${models_path} (${free_note})."
    printf "Указать другую папку/диск для них? Путь, или Enter чтобы оставить как есть: "
    read -r custom_path </dev/tty
    if [ -n "$custom_path" ]; then
        mkdir -p "$custom_path"
        echo "Чтобы Ollama использовала эту папку, добавьте в свой ~/.bashrc (или ~/.zshrc):"
        echo "  export OLLAMA_MODELS=\"$custom_path\""
        echo "...и перезапустите Ollama (systemctl restart ollama, либо заново её запустить) перед скачиванием моделей."
        export OLLAMA_MODELS="$custom_path"
        models_path="$custom_path"
        free_gb=$(free_space_gb "$models_path")
    fi

    # Pick models that actually fit this machine - both RAM and disk space.
    mem_gb=0
    if [ -r /proc/meminfo ]; then
        mem_gb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
    elif command -v sysctl >/dev/null 2>&1; then
        mem_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
    fi
    gpu_note=""
    command -v nvidia-smi >/dev/null 2>&1 && gpu_note=", есть видеокарта NVIDIA (модели будут работать быстро)"

    text_model_for() {
        case "$1" in
            1) echo "llama3.2:3b" ;; 2) echo "llama3" ;;
            3) echo "qwen2.5:14b" ;; 4) echo "qwen2.5:32b" ;;
        esac
    }
    if [ "$mem_gb" -lt 8 ]; then ram_rec=1; elif [ "$mem_gb" -lt 16 ]; then ram_rec=2; elif [ "$mem_gb" -le 32 ]; then ram_rec=3; else ram_rec=4; fi
    # Step down from the RAM-based pick while it wouldn't fit on disk (+2 GB
    # headroom) - a recommendation the drive can't hold is worse than none.
    rec=$ram_rec
    if [ -n "$free_gb" ]; then
        while [ "$rec" -gt 1 ]; do
            need=$(( $(model_size_gb "$(text_model_for "$rec")") + 2 ))
            [ "$need" -le "$free_gb" ] && break
            rec=$((rec - 1))
        done
    fi
    disk_note=""
    [ "$rec" != "$ram_rec" ] && disk_note=" (модель $(text_model_for "$ram_rec") не рекомендую - не хватит места на диске)"
    echo ""
    echo "Ваша система: ОЗУ ${mem_gb} ГБ${gpu_note}."
    echo "Текстовая модель (мозг бота):"
    echo "  0) Пропустить - модели пока не скачивать (бот запустится, скачаете позже)"
    echo "  1) llama3.2:3b — лёгкая и быстрая (~2 ГБ на диске, ~4 ГБ ОЗУ)"
    echo "  2) llama3 (8B) — баланс качества и скорости (~5 ГБ на диске, ~8 ГБ ОЗУ)"
    echo "  3) qwen2.5:14b — заметно умнее (~9 ГБ на диске, ~12–16 ГБ ОЗУ)"
    echo "  4) qwen2.5:32b — максимум качества (~20 ГБ на диске, ~24+ ГБ ОЗУ)"
    printf "Выбор [%s — рекомендуется для вашей системы%s]: " "$rec" "$disk_note"
    read -r model_choice </dev/tty
    if [ "${model_choice:-$rec}" = "0" ]; then
        SKIP_MODEL_DOWNLOAD=1
        echo "Модели скачивать не будем сейчас - бот запустится без них."
        return
    fi
    case "${model_choice:-$rec}" in
        1) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=llama3.2:3b|" .env ;;
        3) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=qwen2.5:14b|" .env ;;
        4) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=qwen2.5:32b|" .env ;;
        *) : ;;  # 2 = llama3, already the default in .env.example
    esac

    vision_model_for() {
        case "$1" in 1) echo "llama3.2-vision" ;; 3) echo "moondream" ;; *) echo "qwen2.5vl:7b" ;; esac
    }
    vision_ram_rec=2
    [ "$mem_gb" -lt 8 ] && vision_ram_rec=3
    vision_rec=$vision_ram_rec
    if [ -n "$free_gb" ]; then
        while [ "$vision_rec" -gt 1 ]; do
            need=$(( $(model_size_gb "$(vision_model_for "$vision_rec")") + 2 ))
            [ "$need" -le "$free_gb" ] && break
            vision_rec=$((vision_rec - 1))
        done
    fi
    echo ""
    echo "Модель для анализа фото (vision) - бот распознаёт, что на картинке, а не рисует их:"
    echo "  1) llama3.2-vision (11B) - от Meta, надёжный универсальный выбор (~8 ГБ на диске, ~10 ГБ ОЗУ)"
    echo "  2) qwen2.5vl:7b - легче и часто точнее на бенчмарках (~6 ГБ на диске, ~6 ГБ ОЗУ)"
    echo "  3) moondream - совсем лёгкая и быстрая, слабее качеством - для слабого железа (~2 ГБ на диске, ~3 ГБ ОЗУ)"
    printf "Выбор [%s — рекомендуется для вашей системы]: " "$vision_rec"
    read -r vision_choice </dev/tty
    chosen_vision=$(vision_model_for "${vision_choice:-$vision_rec}")
    sed_i "s|^VISION_MODEL=.*|VISION_MODEL=${chosen_vision}|" .env
}

# ---- launch containers + pull models ------------------------------------
setup_ollama_and_launch() {
    # Use Ollama on the host if it's already running, otherwise offer docker.
    OLLAMA_SKIP=0
    if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
        OLLAMA_IN_DOCKER=0
    else
        echo ""
        echo "Ollama на хосте не найдена (либо ещё не запустилась)."
        printf "Запустить Ollama в docker-контейнере и скачать в неё модели (несколько ГБ)? y/n [y]: "
        read -r run_in_docker </dev/tty
        if [ "${run_in_docker:-y}" = "n" ]; then
            echo "Пропускаю. Установите Ollama сами (https://ollama.com) или укажите OLLAMA_API_BASE в .env."
            OLLAMA_IN_DOCKER=0
            OLLAMA_SKIP=1
        else
            OLLAMA_IN_DOCKER=1
            api_base=$(grep -E "^OLLAMA_API_BASE=" .env || true)
            if echo "$api_base" | grep -qE "host\.docker\.internal|localhost|127\.0\.0\.1"; then
                sed_i "s|^OLLAMA_API_BASE=.*|OLLAMA_API_BASE=http://ollama:11434/v1|" .env
            elif [ -n "$api_base" ] && ! echo "$api_base" | grep -q "//ollama:"; then
                echo "В .env задан свой OLLAMA_API_BASE — оставляю его как есть."
            fi
            grep -q "^COMPOSE_PROFILES=" .env || echo "COMPOSE_PROFILES=ollama" >> .env
        fi
    fi

    launch_containers

    TEXT_MODEL=$(grep -E "^TEXT_MODEL=" .env | cut -d= -f2- || true)
    VISION_MODEL=$(grep -E "^VISION_MODEL=" .env | cut -d= -f2- || true)
    TEXT_MODEL=${TEXT_MODEL:-llama3}
    VISION_MODEL=${VISION_MODEL:-llama3.2-vision}

    if [ "$OLLAMA_SKIP" = "1" ]; then
        echo "Ollama не настроена — модели не скачаны. Позже: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
    elif [ "$OLLAMA_IN_DOCKER" = "1" ]; then
        echo "Жду запуска Ollama в контейнере..."
        ready=0
        for _ in $(seq 1 30); do
            if docker compose exec ollama ollama list >/dev/null 2>&1; then ready=1; break; fi
            sleep 2
        done
        if [ "$ready" != "1" ]; then
            echo "Ollama в контейнере не отвечает. Скачайте модели вручную: docker compose exec ollama ollama pull $TEXT_MODEL"
            return
        fi
        choose_and_pull_models "docker compose exec ollama ollama"
    elif command -v ollama >/dev/null 2>&1; then
        # Ollama on the host with a CLI available - can pull straight in
        choose_and_pull_models "ollama"
    else
        echo "Убедитесь, что модели скачаны: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
    fi
}

pull_one() {
    # $1 = pull command prefix (multi-word, intentionally unquoted), $2 = model
    size=$(model_size_gb "$2")
    if [ -n "$size" ]; then size_note=" (~${size} ГБ, прогресс скачивания покажется ниже)"; else size_note=" (размер неизвестен, прогресс скачивания покажется ниже)"; fi
    echo "Скачиваю $2${size_note}..."
    # Not redirected/suppressed on purpose - 'ollama pull' draws its own
    # live progress bar (%, speed, ETA) on this same terminal.
    if $1 pull "$2"; then
        echo "$2 скачана."
    else
        echo "Скачивание $2 завершилось с ошибкой - см. вывод выше."
    fi
}

# Ask which models to download now, then pull them. $1 = pull command prefix
# ("docker compose exec ollama ollama" or "ollama").
choose_and_pull_models() {
    if [ "${SKIP_MODEL_DOWNLOAD:-0}" = "1" ]; then
        echo "Модели пропущены на предыдущем шаге. Позже: $1 pull $TEXT_MODEL; $1 pull $VISION_MODEL"
        return
    fi
    echo ""
    echo "Скачать нейросети сейчас? Это самый большой объём (модели по несколько ГБ)."
    echo "  1) Скачать обе: $TEXT_MODEL (текст) + $VISION_MODEL (фото) — рекомендуется"
    echo "  2) Только текстовую: $TEXT_MODEL"
    echo "  3) Только для фото (vision): $VISION_MODEL"
    echo "  4) Не скачивать сейчас (бот запустится, модели скачаете позже)"
    printf "Выбор [1]: "
    read -r dl </dev/tty
    case "${dl:-1}" in
        2) pull_one "$1" "$TEXT_MODEL" ;;
        3) pull_one "$1" "$VISION_MODEL" ;;
        4) echo "Пропущено. Позже скачать: $1 pull $TEXT_MODEL && $1 pull $VISION_MODEL" ;;
        *) pull_one "$1" "$TEXT_MODEL"; pull_one "$1" "$VISION_MODEL" ;;
    esac
}

# Build+start, or pull+start in auto-update mode (COMPOSE_FILE set)
launch_containers() {
    if grep -q "^COMPOSE_FILE=" .env; then
        echo "Скачиваю готовый образ и запускаю контейнеры..."
        docker compose up -d
    else
        echo "Собираю и запускаю контейнеры..."
        docker compose up -d --build
    fi
}

print_done() {
    echo ""
    echo "=== Готово! ==="
    echo "Меню управления:  bash install.sh"
    echo "Логи бота:        docker compose logs -f bot"
    echo "Остановить:       docker compose down"
}

# ---- menu actions (bot already installed) -------------------------------
do_update() {
    if [ -d .git ]; then
        echo "Забираю обновления из репозитория..."
        git pull --ff-only || echo "git pull не удался — продолжаю с текущим кодом."
    fi
    launch_containers
    echo "Обновление завершено."
}

do_reinstall() {
    echo "Пересобираю и пересоздаю контейнеры (настройки и данные сохраняются)..."
    if grep -q "^COMPOSE_FILE=" .env; then
        docker compose up -d --force-recreate
    else
        docker compose up -d --build --force-recreate
    fi
    echo "Переустановка завершена."
}

do_change_token() {
    printf "Введите новый BOT_TOKEN (Enter = отмена): "
    read -r token </dev/tty
    [ -n "$token" ] || { echo "Отменено."; return; }
    sed_i "s|^BOT_TOKEN=.*|BOT_TOKEN=${token}|" .env
    echo "Токен обновлён, перезапускаю бота..."
    docker compose up -d
    echo "Готово."
}

# The only model repos imagegen's own installer offers (see
# imagegen/install.sh's model choice) - used below to find what's safe to
# delete from the *shared* HF cache without touching unrelated models some
# other tool might have cached there.
IMAGEGEN_MODEL_REPOS="models--stabilityai--sd-turbo models--stabilityai--sdxl-turbo models--stabilityai--stable-diffusion-xl-base-1.0"

do_remove() {
    echo ""
    echo "!!! ПОЛНОЕ УДАЛЕНИЕ !!!"
    echo "Будет удалено БЕЗВОЗВРАТНО:"
    echo "  • контейнеры бота и Redis (и Ollama, если она в docker);"
    echo "  • docker-образ бота (собранный локально или подтянутый с ghcr.io);"
    echo "  • история всех диалогов и напоминания;"
    echo "  • настройки (.env) и все резервные копии в data/backups."
    echo "Скачанные модели Ollama по умолчанию НЕ трогаются (чтобы не качать заново)."
    echo "Саму программу Ollama установщик не удаляет — только docker-контейнер."
    has_imagegen=0
    [ -d imagegen/venv ] && has_imagegen=1
    [ "$has_imagegen" = "1" ] && echo "Отдельно спрошу про сервис генерации картинок (imagegen) - venv и скачанные модели, обычно самое тяжёлое."
    printf "Точно удалить? Впишите 'delete' для подтверждения: "
    read -r confirm </dev/tty
    [ "$confirm" = "delete" ] || { echo "Отменено — ничего не тронуто."; return; }

    printf "Удалить ТАКЖЕ скачанные модели Ollama (только если она в docker; несколько ГБ)? y/n [n]: "
    read -r delmodels </dev/tty

    echo "Останавливаю и удаляю контейнеры и образ..."
    if [ "${delmodels:-n}" = "y" ]; then
        docker compose down -v --rmi local 2>/dev/null || docker compose down -v 2>/dev/null || true
        echo "Модели Ollama в docker тоже удалены."
    else
        docker compose down --rmi local 2>/dev/null || docker compose down 2>/dev/null || true
    fi
    # --rmi local only removes an image docker compose *built* itself - in
    # auto-update mode (COMPOSE_FILE set) the bot runs a *pulled* ghcr.io
    # image instead, which --rmi local silently leaves behind.
    ghcr_image="ghcr.io/mondaydecember/aibot-master.pro:latest"
    [ -n "$(docker images -q "$ghcr_image" 2>/dev/null)" ] && docker rmi "$ghcr_image" >/dev/null 2>&1
    rm -rf data .env
    echo "Бот и все данные удалены."

    if [ "$has_imagegen" = "1" ]; then
        hf_hub="$HOME/.cache/huggingface/hub"
        size_kb=0
        [ -d imagegen/venv ] && size_kb=$(( size_kb + $(du -sk imagegen/venv 2>/dev/null | cut -f1) ))
        for repo in $IMAGEGEN_MODEL_REPOS; do
            [ -d "$hf_hub/$repo" ] && size_kb=$(( size_kb + $(du -sk "$hf_hub/$repo" 2>/dev/null | cut -f1) ))
        done
        size_gb=$(( size_kb / 1024 / 1024 ))
        printf "Удалить также imagegen - venv и скачанные модели (~%s ГБ)? y/n [n]: " "$size_gb"
        read -r delimagegen </dev/tty
        if [ "${delimagegen:-n}" = "y" ]; then
            rm -rf imagegen/venv imagegen/.env
            for repo in $IMAGEGEN_MODEL_REPOS; do rm -rf "${hf_hub:?}/$repo"; done
            echo "imagegen удалён (~${size_gb} ГБ освобождено)."
        else
            echo "imagegen оставлен нетронутым."
        fi
    fi

    printf "Удалить также саму папку с программой? y/n [n]: "
    read -r delfolder </dev/tty
    if [ "${delfolder:-n}" = "y" ]; then
        folder=$(basename "$PWD"); parent=$(dirname "$PWD")
        cd "$parent" && rm -rf "$folder" && echo "Папка '$folder' удалена. Готово."
    else
        echo "Папка оставлена. Установить заново: bash install.sh"
    fi
}

show_menu() {
    while true; do
        echo ""
        echo "=== aibot-master — бот уже установлен ==="
        echo "  1) Обновить (скачать новую версию и перезапустить)"
        echo "  2) Переустановить (пересобрать контейнеры, настройки сохранить)"
        echo "  3) Сменить токен бота Telegram"
        echo "  4) Изменить настройки (язык, доступ, модели...)"
        echo "  5) Удалить ПОЛНОСТЬЮ (стереть бота и ВСЕ данные — безвозвратно)"
        echo "  0) Выход"
        printf "Выбор: "
        read -r choice </dev/tty
        case "$choice" in
            1) do_update ;;
            2) do_reinstall ;;
            3) do_change_token ;;
            4) bash configure.sh ;;
            5) do_remove; break ;;
            0) break ;;
            *) echo "Введите число от 0 до 5." ;;
        esac
    done
}

# ---- entry point --------------------------------------------------------
main() {
    require_docker

    # Clone unless already running inside the repo
    if [ ! -f docker-compose.yml ]; then
        command -v git >/dev/null 2>&1 || { echo "Ошибка: git не установлен."; exit 1; }
        [ -d "$DIR" ] || git clone "$REPO_URL" "$DIR"
        cd "$DIR"
    fi

    mkdir -p data
    if [ -f bot_data.db ]; then
        mv bot_data.db data/bot_data.db
        echo "Перенёс bot_data.db со старого пути в data/."
    fi

    if [ ! -f .env ]; then
        # No settings yet -> fresh install
        echo "=== Установка aibot-master ==="
        run_wizard
        setup_ollama_and_launch
        print_done
    elif bot_installed; then
        # Settings AND a bot container exist -> management menu
        show_menu
    else
        # Settings exist but the bot was never launched -> finish the install
        echo "Настройки (.env) найдены, но бот ещё не запущен — завершаю установку..."
        setup_ollama_and_launch
        print_done
    fi
}

# "Installed" = the bot container has actually been created, not just an .env
# left over from an aborted setup.
bot_installed() {
    [ -n "$(docker ps -a --filter 'name=^aiogram_bot$' -q 2>/dev/null)" ]
}

main
