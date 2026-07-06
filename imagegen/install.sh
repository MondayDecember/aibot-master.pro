#!/usr/bin/env bash
# One-time setup for the local image-generation service (Linux).
# Usage: bash install.sh
# On Linux there's no DirectML - the backend is CUDA (NVIDIA) or CPU.
set -uo pipefail
cd "$(dirname "$0")"

echo "=== Настройка сервиса генерации картинок (Linux) ==="

command -v python3 >/dev/null 2>&1 || {
    echo "Ошибка: нужен python3 (sudo apt install -y python3 python3-venv python3-pip)."
    exit 1
}
python3 -c "import venv" 2>/dev/null || {
    echo "Ошибка: нет модуля venv (sudo apt install -y python3-venv)."
    exit 1
}

[ -d venv ] || python3 -m venv venv
./venv/bin/python -m pip install -q --upgrade pip

set_backend_env() {
    # Persist the chosen backend into imagegen/.env so run.sh uses it.
    [ -f .env ] || { [ -f .env.example ] && cp .env.example .env || touch .env; }
    if grep -qE '^\s*IMAGEGEN_BACKEND=' .env; then
        sed -i.bak "s|^[[:space:]]*IMAGEGEN_BACKEND=.*|IMAGEGEN_BACKEND=$1|" .env && rm -f .env.bak
    else
        echo "IMAGEGEN_BACKEND=$1" >> .env
    fi
    echo "Записал IMAGEGEN_BACKEND=$1 в imagegen/.env"
}

if command -v nvidia-smi >/dev/null 2>&1; then
    echo "Обнаружена видеокарта NVIDIA — ставлю ускоренный путь CUDA."
    printf "Версия CUDA-колёс: cu128 (50-й ряд/новые), cu124 (40/30) [cu128]: "
    read -r cuda || true
    cuda=${cuda:-cu128}
    echo "Ставлю torch (CUDA $cuda) — несколько ГБ, займёт время..."
    ./venv/bin/python -m pip install torch --index-url "https://download.pytorch.org/whl/$cuda"
    ./venv/bin/python -m pip install -q -r requirements-cuda.txt
    set_backend_env cuda
else
    echo "Видеокарта NVIDIA не найдена — ставлю CPU-режим (работает, но картинки медленные)."
    ./venv/bin/python -m pip install -q torch
    ./venv/bin/python -m pip install -q -r requirements-cuda.txt
    set_backend_env cpu
fi

echo ""
echo "=== Готово ==="
echo "Запуск:  bash run.sh"
echo "Модель (~1 ГБ для SD-Turbo) скачается при первом запросе картинки, не при старте."
echo "Автозапуск вместе с системой — см. пример systemd-сервиса в README.md."
