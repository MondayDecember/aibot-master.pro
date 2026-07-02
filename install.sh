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
else
    echo "Файл .env уже существует — оставляю как есть."
fi

# Use Ollama on the host if it's already running, otherwise run it in docker
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Найдена Ollama на хосте (localhost:11434) — бот будет использовать её."
    OLLAMA_IN_DOCKER=0
else
    echo "Ollama на хосте не найдена — запускаю её в docker-контейнере."
    OLLAMA_IN_DOCKER=1
    sed_i "s|^OLLAMA_API_BASE=.*|OLLAMA_API_BASE=http://ollama:11434/v1|" .env
    # COMPOSE_PROFILES in .env makes plain 'docker compose up -d' include ollama
    grep -q "^COMPOSE_PROFILES=" .env || echo "COMPOSE_PROFILES=ollama" >> .env
fi

echo "Собираю и запускаю контейнеры..."
docker compose up -d --build

# Pull the models the bot needs
TEXT_MODEL=$(grep -E "^TEXT_MODEL=" .env | cut -d= -f2- || true)
VISION_MODEL=$(grep -E "^VISION_MODEL=" .env | cut -d= -f2- || true)
TEXT_MODEL=${TEXT_MODEL:-llama3}
VISION_MODEL=${VISION_MODEL:-llama3.2-vision}

if [ "$OLLAMA_IN_DOCKER" = "1" ]; then
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
