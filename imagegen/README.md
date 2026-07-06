# imagegen — local image generation for the bot

A small local HTTP service that turns text prompts into images (`/imagine <prompt>` in the bot). Runs **natively on the host**, not in Docker — see below for why.

## Why not a docker-compose service (like `ollama`)?

On **Windows** Docker Desktop, GPU passthrough into containers isn't reliably available for either DirectML or CUDA (`docker run --gpus all ...` fails with *"WSL environment detected but no adapters were found"* even when the same GPU works fine for natively-running apps). That's also why Ollama itself runs natively on the host here instead of in its optional docker profile. So this service runs natively on the host and the bot talks to it over HTTP.

On **Linux**, docker GPU passthrough (via `nvidia-container-toolkit`) does work well, but for consistency the same native-host + HTTP setup is used — install with `bash install.sh` / `bash run.sh` below.

## Backends: CUDA (NVIDIA) vs DirectML (anything)

The service supports two compute backends, chosen by `IMAGEGEN_BACKEND` (default `auto`):

- **CUDA** — native NVIDIA path. Much faster on NVIDIA cards, and runs the model in fp16 (half the VRAM, roughly double the speed). Use this on any GeForce/RTX card, including the RTX 50-series. Needs a CUDA build of torch — `install.ps1` installs it for you from the CUDA wheel index.
- **DirectML** — [DirectML](https://github.com/microsoft/DirectML) sits on top of DirectX 12, so the *same* code runs on **AMD, Intel, and NVIDIA** GPUs — **Windows only**. Portable but slower than a card's native API. On an AMD Radeon RX 7800 XT, SD-Turbo (1 step) generates a 512x512 image in ~5 seconds.
- **CPU** — fallback with no GPU. Works everywhere but slow (tens of seconds per image).

`auto` picks CUDA if an NVIDIA GPU is present, otherwise DirectML (Windows) / CPU (Linux). Force a specific one with `IMAGEGEN_BACKEND=cuda|directml|cpu`.

## Setup — Windows

```
cd imagegen
.\install.ps1
.\run.ps1
```

`install.ps1` detects an NVIDIA GPU and offers the CUDA path (recommended on NVIDIA); on AMD/Intel it uses DirectML. It writes the chosen `IMAGEGEN_BACKEND` into `imagegen/.env`. For the RTX 50-series (Blackwell) pick the **cu128** wheels when asked; for 40/30-series **cu124** also works.

## Setup — Linux (e.g. Ubuntu Server 24.04)

```
cd imagegen
bash install.sh
bash run.sh
```

`install.sh` uses CUDA if `nvidia-smi` is present (torch from the CUDA wheel index — pick **cu128** for the RTX 50-series), otherwise CPU. There's no DirectML on Linux. Needs `python3` + `python3-venv` (`sudo apt install -y python3 python3-venv python3-pip`).

To start it automatically on boot, use a systemd service, e.g. `/etc/systemd/system/aibot-imagegen.service`:

```ini
[Unit]
Description=aibot image generation
After=network.target

[Service]
WorkingDirectory=/home/youruser/aibot-master/imagegen
ExecStart=/home/youruser/aibot-master/imagegen/run.sh
Restart=on-failure
User=youruser

[Install]
WantedBy=multi-user.target
```

Then `sudo systemctl enable --now aibot-imagegen`.

Check what it picked (either OS): open `http://localhost:7861/health` — it reports `"backend"` and `"devices"`.

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
| `IMAGEGEN_BACKEND` | `auto` | `auto` (CUDA on NVIDIA, else DirectML, else CPU) or force `cuda` / `directml` / `cpu`. |
| `IMAGEGEN_DEVICES` | `` (card 0) | Which GPUs to use: empty = card 0, `all` = every detected card, `0,1` = specific ones. |
| `IMAGEGEN_API_KEY` | `` (no auth) | Shared secret; must match `IMAGEGEN_API_KEY` in the bot's `.env`. |

In the bot's own `.env`, see `IMAGEGEN_ENABLED` / `IMAGEGEN_API_BASE` / `IMAGEGEN_API_KEY`.

## Multiple GPUs

Set `IMAGEGEN_DEVICES=all` (or a list like `0,1`) to spread work across several cards. Each card loads its own copy of the model and handles one generation at a time; the service round-robins requests across them, so N cards serve N images **simultaneously**. This is throughput, not latency — a single image still runs on one card at its normal speed (diffusion isn't split across GPUs here). Useful when several people use `/imagine` at once. Note each card needs enough VRAM for its own full copy of the model.
