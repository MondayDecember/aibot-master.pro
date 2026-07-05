# imagegen — local image generation for the bot

A small local HTTP service that turns text prompts into images (`/imagine <prompt>` in the bot). Runs **natively on the host**, not in Docker — see below for why.

## Why not a docker-compose service (like `ollama`)?

GPU passthrough into Windows Docker Desktop containers isn't reliably available for either DirectML or CUDA on this kind of setup (`docker run --gpus all ...` fails with *"WSL environment detected but no adapters were found"* even when the same GPU works fine for natively-running apps). That's also why Ollama itself runs natively on the host here instead of in its optional docker profile. Same story for this service.

## Why DirectML instead of CUDA/ROCm

[DirectML](https://github.com/microsoft/DirectML) sits on top of DirectX 12, so the *same* code runs on AMD, NVIDIA, and Intel GPUs on Windows. Useful specifically because the GPU in this box is expected to change (AMD Radeon now, an NVIDIA Tesla P100 later) — one implementation instead of a CUDA path and a ROCm path to maintain.

Trade-off: DirectML is generally a bit slower than a card's native API (CUDA on NVIDIA, ROCm on AMD/Linux) for the same GPU. On an AMD Radeon RX 7800 XT, SD-Turbo (1 step) generates a 512x512 image in **~5 seconds** — plenty fast for a Telegram bot.

## Setup

```
cd imagegen
.\install.ps1
.\run.ps1
```

First request downloads the model (~1 GB for SD-Turbo, cached in `%USERPROFILE%\.cache\huggingface` afterwards). The service listens on `http://localhost:7861`; the bot (in Docker) reaches it at `http://host.docker.internal:7861`, same pattern as `OLLAMA_API_BASE`.

To have it start automatically with Windows, add `run.ps1` to Task Scheduler with a "At log on" trigger — the same way people usually set up Ollama to auto-start.

## Configuration

Environment variables (set before running `run.ps1`, or edit `app.py`):

| Variable | Default | Meaning |
|---|---|---|
| `IMAGEGEN_MODEL` | `stabilityai/sd-turbo` | Any diffusers-compatible text-to-image model on Hugging Face. `stabilityai/sdxl-turbo` is a heavier, higher-quality alternative (~7 GB, slower). |
| `IMAGEGEN_STEPS` | `1` | Inference steps. `sd-turbo`/`sdxl-turbo` are distilled for 1-4 steps - more steps mostly just costs time with these models. |
| `IMAGEGEN_GUIDANCE_SCALE` | `0.0` | Turbo models are trained for guidance-free (CFG=0) generation. |
| `IMAGEGEN_MAX_PROMPT_CHARS` | `500` | Prompts longer than this are truncated. |
| `IMAGEGEN_DEVICES` | `` (card 0) | Which GPUs to use: empty = card 0, `all` = every detected card, `0,1` = specific ones. |
| `IMAGEGEN_API_KEY` | `` (no auth) | Shared secret; must match `IMAGEGEN_API_KEY` in the bot's `.env`. |

In the bot's own `.env`, see `IMAGEGEN_ENABLED` / `IMAGEGEN_API_BASE` / `IMAGEGEN_API_KEY`.

## Multiple GPUs

Set `IMAGEGEN_DEVICES=all` (or a list like `0,1`) to spread work across several cards. Each card loads its own copy of the model and handles one generation at a time; the service round-robins requests across them, so N cards serve N images **simultaneously**. This is throughput, not latency — a single image still runs on one card at its normal speed (diffusion isn't split across GPUs here). Useful when several people use `/imagine` at once. Note each card needs enough VRAM for its own full copy of the model.
