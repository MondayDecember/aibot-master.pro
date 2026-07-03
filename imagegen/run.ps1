# Starts the image-generation service on http://localhost:7861
# (the bot reaches it at http://host.docker.internal:7861, same pattern as Ollama).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path venv)) {
    Write-Host "venv не найден - сначала запустите .\install.ps1" -ForegroundColor Red
    exit 1
}
.\venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 7861
