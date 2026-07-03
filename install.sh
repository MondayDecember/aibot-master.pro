#!/usr/bin/env bash
# One-command installer for aibot-master (Linux/macOS).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.sh | bash
# Or from a cloned repo: bash install.sh
set -euo pipefail

REPO_URL="https://github.com/MondayDecember/aibot-master.pro.git"
DIR="aibot-master"

echo "=== Установка aibot-master ==="

command -v docker >/dev/null 2>&1 || {
    echo "Ошибка: Docker не установлен. См. https://docs.docker.com/engine/install/"
    exit 1
}
docker compose version >/dev/null 2>&1 || {
    echo "Ошибка: нужен Docker Compose v2 (команда 'docker compose')."
    exit 1
}

# Clone unless the script is already running inside the repo
if [ ! -f docker-compose.yml ]; then
    command -v git >/dev/null 2>&1 || { echo "Ошибка: git не установлен."; exit 1; }
    [ -d "$DIR" ] || git clone "$REPO_URL" "$DIR"
    cd "$DIR"
fi

# The bot stores its sqlite db in ./data (bind-mounted into the container)
mkdir -p data
if [ -f bot_data.db ]; then
    mv bot_data.db data/bot_data.db
    echo "Перенёс bot_data.db со старого пути в data/."
fi

# portable in-place sed (GNU and BSD/macOS)
sed_i() { sed -i.bak "$1" "$2" && rm -f "$2.bak"; }

if [ ! -f .env ]; then
    cp .env.example .env
    printf "Введите BOT_TOKEN (получить у @BotFather в Telegram): "
    read -r token </dev/tty
    [ -n "$token" ] || { echo "Ошибка: токен пустой."; exit 1; }
    sed_i "s|^BOT_TOKEN=.*|BOT_TOKEN=${token}|" .env

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

    echo ""
    echo "Модель для анализа фото (vision) - бот распознаёт, что на картинке, а не рисует их:"
    echo "  1) llama3.2-vision (11B) - от Meta, надёжный универсальный выбор"
    echo "  2) qwen2.5vl:7b - легче и часто точнее на бенчмарках (по умолчанию)"
    echo "  3) moondream - совсем лёгкая и быстрая, слабее качеством - для слабого железа"
    printf "Выбор [2]: "
    read -r vision_choice </dev/tty
    case "${vision_choice:-2}" in
        1) chosen_vision="llama3.2-vision" ;;
        3) chosen_vision="moondream" ;;
        *) chosen_vision="qwen2.5vl:7b" ;;
    esac
    sed_i "s|^VISION_MODEL=.*|VISION_MODEL=${chosen_vision}|" .env
else
    echo "Файл .env уже существует — оставляю как есть (настройки: bash configure.sh)."
fi

# Use Ollama on the host if it's already running, otherwise run it in docker.
# Only touch OLLAMA_API_BASE while it still points to a default location -
# a custom value (e.g. a remote Ollama server) must be left alone.
OLLAMA_SKIP=0
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
    OLLAMA_IN_DOCKER=0
else
    echo ""
    echo "Ollama на хосте не найдена (либо ещё не запустилась - проверьте, что она точно не работает)."
    printf "Запустить Ollama в отдельном docker-контейнере и скачать в неё модели (несколько ГБ, займёт время и место на диске)? y/n [y]: "
    read -r run_in_docker </dev/tty
    if [ "${run_in_docker:-y}" = "n" ]; then
        echo "Пропускаю. Установите Ollama сами (https://ollama.com) или укажите свой OLLAMA_API_BASE в .env, затем: docker compose up -d"
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
        # COMPOSE_PROFILES in .env makes plain 'docker compose up -d' include ollama
        grep -q "^COMPOSE_PROFILES=" .env || echo "COMPOSE_PROFILES=ollama" >> .env
    fi
fi

if grep -q "^COMPOSE_FILE=" .env; then
    # Auto-update mode: run from the prebuilt registry image, don't build
    echo "Скачиваю готовый образ и запускаю контейнеры..."
    docker compose up -d
else
    echo "Собираю и запускаю контейнеры..."
    docker compose up -d --build
fi

# Pull the models the bot needs
TEXT_MODEL=$(grep -E "^TEXT_MODEL=" .env | cut -d= -f2- || true)
VISION_MODEL=$(grep -E "^VISION_MODEL=" .env | cut -d= -f2- || true)
TEXT_MODEL=${TEXT_MODEL:-llama3}
VISION_MODEL=${VISION_MODEL:-llama3.2-vision}

if [ "$OLLAMA_SKIP" = "1" ]; then
    echo "Модели не скачаны - настройте свою Ollama и выполните: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
elif [ "$OLLAMA_IN_DOCKER" = "1" ]; then
    # Wait until the ollama server inside the container answers
    echo "Жду запуска Ollama в контейнере..."
    ready=0
    for _ in $(seq 1 30); do
        if docker compose exec ollama ollama list >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 2
    done
    if [ "$ready" != "1" ]; then
        echo "Ollama в контейнере не отвечает. Скачайте модели вручную: docker compose exec ollama ollama pull $TEXT_MODEL"
        exit 1
    fi
    echo "Скачиваю модели (может занять много времени, они большие)..."
    docker compose exec ollama ollama pull "$TEXT_MODEL"
    docker compose exec ollama ollama pull "$VISION_MODEL"
else
    echo "Убедитесь, что модели скачаны: ollama pull $TEXT_MODEL && ollama pull $VISION_MODEL"
fi

echo ""
echo "=== Готово! ==="
echo "Логи бота:      docker compose logs -f bot"
echo "Остановить:     docker compose down"
echo "Обновить:       git pull && docker compose up -d --build"
