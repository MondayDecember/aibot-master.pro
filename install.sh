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

    # Pick models that actually fit this machine
    mem_gb=0
    if [ -r /proc/meminfo ]; then
        mem_gb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
    elif command -v sysctl >/dev/null 2>&1; then
        mem_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
    fi
    gpu_note=""
    command -v nvidia-smi >/dev/null 2>&1 && gpu_note=", есть видеокарта NVIDIA (модели будут работать быстро)"

    if [ "$mem_gb" -lt 8 ]; then rec=1; elif [ "$mem_gb" -lt 16 ]; then rec=2; elif [ "$mem_gb" -lt 32 ]; then rec=3; else rec=4; fi
    echo ""
    echo "Ваша система: ОЗУ ${mem_gb} ГБ${gpu_note}."
    echo "Текстовая модель (мозг бота):"
    echo "  1) llama3.2:3b — лёгкая и быстрая (~4 ГБ ОЗУ)"
    echo "  2) llama3 (8B) — баланс качества и скорости (~8 ГБ ОЗУ)"
    echo "  3) qwen2.5:14b — заметно умнее (~12–16 ГБ ОЗУ)"
    echo "  4) qwen2.5:32b — максимум качества (~24+ ГБ ОЗУ)"
    printf "Выбор [%s — рекомендуется для вашей системы]: " "$rec"
    read -r model_choice </dev/tty
    case "${model_choice:-$rec}" in
        1) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=llama3.2:3b|" .env ;;
        3) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=qwen2.5:14b|" .env ;;
        4) sed_i "s|^TEXT_MODEL=.*|TEXT_MODEL=qwen2.5:32b|" .env ;;
        *) : ;;  # 2 = llama3, already the default in .env.example
    esac

    vision_rec=2
    [ "$mem_gb" -lt 8 ] && vision_rec=3
    echo ""
    echo "Модель для анализа фото (vision) - бот распознаёт, что на картинке, а не рисует их:"
    echo "  1) llama3.2-vision (11B) - от Meta, надёжный универсальный выбор (~10 ГБ ОЗУ)"
    echo "  2) qwen2.5vl:7b - легче и часто точнее на бенчмарках (~6 ГБ ОЗУ)"
    echo "  3) moondream - совсем лёгкая и быстрая, слабее качеством - для слабого железа (~3 ГБ ОЗУ)"
    printf "Выбор [%s — рекомендуется для вашей системы]: " "$vision_rec"
    read -r vision_choice </dev/tty
    case "${vision_choice:-$vision_rec}" in
        1) chosen_vision="llama3.2-vision" ;;
        3) chosen_vision="moondream" ;;
        *) chosen_vision="qwen2.5vl:7b" ;;
    esac
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
        echo "Модели не скачаны - настройте Ollama и выполните: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
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
        echo "Скачиваю модели (может занять много времени, они большие)..."
        docker compose exec ollama ollama pull "$TEXT_MODEL"
        docker compose exec ollama ollama pull "$VISION_MODEL"
    else
        echo "Убедитесь, что модели скачаны: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
    fi
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

do_remove() {
    echo ""
    echo "!!! ПОЛНОЕ УДАЛЕНИЕ !!!"
    echo "Будет удалено БЕЗВОЗВРАТНО:"
    echo "  • контейнеры бота и Redis (и Ollama, если она в docker);"
    echo "  • собранный docker-образ бота;"
    echo "  • история всех диалогов и напоминания;"
    echo "  • настройки (.env) и все резервные копии в data/backups."
    echo "Скачанные модели Ollama по умолчанию НЕ трогаются (чтобы не качать заново)."
    echo "Саму программу Ollama установщик не удаляет — только docker-контейнер."
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
    rm -rf data .env
    echo "Бот и все данные удалены."

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
        echo "  1) Обновить (забрать новую версию и перезапустить)"
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

    if [ -f .env ]; then
        # Already installed -> management menu
        show_menu
    else
        echo "=== Установка aibot-master ==="
        run_wizard
        setup_ollama_and_launch
        print_done
    fi
}

main
