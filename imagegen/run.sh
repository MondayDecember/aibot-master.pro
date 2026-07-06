#!/usr/bin/env bash
# Starts the image-generation service on http://localhost:7861
# The bot (in docker) reaches it at http://host.docker.internal:7861 - the
# compose file maps that to the host gateway, so it works on Linux too.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    echo "venv не найден — сначала запустите: bash install.sh" >&2
    exit 1
fi

exec ./venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 7861
