#!/usr/bin/env bash
# Interactive settings menu for an installed bot (Linux/macOS).
# Usage from the bot folder: bash configure.sh
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Файл .env не найден — сначала выполните установку (install.sh)."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Docker не установлен."; exit 1; }

# The menu runs inside the bot image (python is guaranteed there), with the
# host .env mounted in. ':' is the COMPOSE_FILE separator on linux/mac.
# --user root: the mounted .env may be owned by root (typical VPS installs),
# and the container's default non-root user couldn't save it.
if docker compose run --rm --no-deps --user root -v "$(pwd)/.env:/app/.env" bot \
    python tools/configure.py --env /app/.env --sep :; then
    echo "Применяю настройки (перезапуск бота)..."
    docker compose up -d
    echo "Готово."
fi
