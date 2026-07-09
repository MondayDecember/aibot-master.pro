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

set_model_env() {
    # $1=model $2=steps $3=guidance. Turbo models want steps=1, guidance=0;
    # full SDXL base needs many more steps and non-zero guidance to look
    # right - using turbo settings on it would produce noise.
    [ -f .env ] || { [ -f .env.example ] && cp .env.example .env || touch .env; }
    for pair in "IMAGEGEN_MODEL=$1" "IMAGEGEN_STEPS=$2" "IMAGEGEN_GUIDANCE_SCALE=$3"; do
        key=${pair%%=*}
        if grep -qE "^\s*${key}=" .env; then
            sed -i.bak "s|^[[:space:]]*${key}=.*|${pair}|" .env && rm -f .env.bak
        else
            echo "$pair" >> .env
        fi
    done
    echo "Записал IMAGEGEN_MODEL=$1 (шагов: $2, guidance: $3) в imagegen/.env"
}

if command -v nvidia-smi >/dev/null 2>&1; then
    echo "Обнаружена видеокарта NVIDIA — ставлю ускоренный путь CUDA."
    printf "Версия CUDA-колёс: cu128 (50-й ряд/новые), cu124 (40/30) [cu128]: "
    read -r cuda || true
    cuda=${cuda:-cu128}
    echo "Ставлю torch (CUDA $cuda) — несколько ГБ, займёт время..."
    ./venv/bin/python -m pip install torch --index-url "https://download.pytorch.org/whl/$cuda"
    ./venv/bin/python -m pip install -r requirements-cuda.txt
    set_backend_env cuda
else
    echo "Видеокарта NVIDIA не найдена — ставлю CPU-режим (работает, но картинки медленные)."
    ./venv/bin/python -m pip install torch
    ./venv/bin/python -m pip install -r requirements-cuda.txt
    set_backend_env cpu
fi

echo ""
echo "Какую модель генерации картинок использовать?"
echo "  1) SD-Turbo - лёгкая (~1 ГБ), 1 шаг, пара секунд на картинку"
echo "  2) SDXL-Turbo - заметно качественнее, всё ещё быстрая (~7 ГБ, 1-4 шага)"
echo "  3) SDXL base - максимальное качество (~7 ГБ), но медленнее (20-30 шагов)"
printf "Выбор [1]: "
read -r model_choice || true
case "$model_choice" in
    2) set_model_env "stabilityai/sdxl-turbo" 1 0.0 ;;
    3) set_model_env "stabilityai/stable-diffusion-xl-base-1.0" 30 7.0 ;;
    *) set_model_env "stabilityai/sd-turbo" 1 0.0 ;;
esac

echo ""
echo "=== Готово ==="
echo "Запуск:  bash run.sh"
echo "Модель скачается при первом запросе картинки, не при старте."
echo "Автозапуск вместе с системой — см. пример systemd-сервиса в README.md."
