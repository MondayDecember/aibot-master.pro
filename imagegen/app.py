"""Minimal local image-generation service (text-to-image).

Runs natively on the host (NOT in Docker - see README.md for why: neither
DirectML nor CUDA GPU passthrough is reliably available inside Windows
Docker Desktop containers). The bot talks to this over HTTP the same way
it talks to Ollama on the host.

Uses DirectML (torch-directml) rather than CUDA/ROCm specifically so the
exact same code runs on AMD, NVIDIA, and Intel GPUs on Windows - useful
here since the GPU in this box is expected to change (AMD now, NVIDIA
later) and nobody wants to maintain two code paths for that.
"""
import io
import logging
import os
import queue
import threading

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from devices import parse_devices

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("IMAGEGEN_MODEL", "stabilityai/sd-turbo")
STEPS = int(os.getenv("IMAGEGEN_STEPS", "1"))
GUIDANCE_SCALE = float(os.getenv("IMAGEGEN_GUIDANCE_SCALE", "0.0"))
MAX_PROMPT_CHARS = int(os.getenv("IMAGEGEN_MAX_PROMPT_CHARS", "500"))
# Which GPUs to use: "" = card 0 only (default), "all" = every card, "0,1" =
# specific ones. Two cards don't make ONE image faster (diffusion isn't split
# across GPUs here), but they serve two requests at once - real throughput.
DEVICES_ENV = os.getenv("IMAGEGEN_DEVICES", "")
# Shared secret; the service binds 0.0.0.0 so this is the only thing stopping
# anyone on the network from POSTing /generate. Empty = no auth.
API_KEY = os.getenv("IMAGEGEN_API_KEY", "").strip()

app = FastAPI(title="aibot-imagegen")


class _Worker:
    """One GPU + its own pipeline. Pulled from the pool exclusively for a
    single generation, so no per-worker lock is needed - the pool queue is
    the mutual exclusion."""

    def __init__(self, index: int):
        self.index = index
        self.pipe = None

    def get_pipe(self):
        if self.pipe is None:
            import torch_directml
            from diffusers import AutoPipelineForText2Image

            device = torch_directml.device(self.index)
            name = torch_directml.device_name(self.index)
            logger.info(f"Loading '{MODEL_ID}' onto device {self.index} ({name})...")
            pipe = AutoPipelineForText2Image.from_pretrained(
                MODEL_ID, torch_dtype=torch.float32, safety_checker=None
            )
            pipe = pipe.to(device)
            # Cuts peak VRAM during the VAE decode step specifically (where
            # OOMs were observed with SDXL-Turbo) by processing the latents
            # in slices instead of all at once - small quality/speed cost,
            # no effect on the UNet steps.
            pipe.enable_vae_slicing()
            pipe.enable_attention_slicing()
            self.pipe = pipe
            logger.info(f"Device {self.index} ready.")
        return self.pipe


# Pool built lazily on first request so `uvicorn app:app` comes up instantly -
# the multi-GB model load only happens once someone actually asks for an image.
# The queue doubles as a semaphore: get() blocks until a GPU is free, giving
# natural round-robin + backpressure across cards.
_pool = None
_pool_devices = []
_pool_init_lock = threading.Lock()


def _get_pool():
    global _pool, _pool_devices
    if _pool is not None:
        return _pool
    with _pool_init_lock:
        if _pool is None:
            import torch_directml

            count = torch_directml.device_count()
            _pool_devices = parse_devices(DEVICES_ENV, count)
            pool = queue.Queue()
            for idx in _pool_devices:
                pool.put(_Worker(idx))
            logger.info(
                f"imagegen device pool: {_pool_devices} "
                f"({count} DirectML device(s) detected)"
            )
            _pool = pool
    return _pool


class GenerateRequest(BaseModel):
    prompt: str
    seed: int | None = None


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_ID,
        "devices": _pool_devices,
        "loaded": _pool is not None,
    }


@app.post("/generate")
def generate(req: GenerateRequest, x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Unauthorized")
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Empty prompt")
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS]

    generator = None
    if req.seed is not None:
        generator = torch.Generator().manual_seed(req.seed)

    pool = _get_pool()
    worker = pool.get()  # blocks until a GPU is free
    try:
        pipe = worker.get_pipe()
        image = pipe(
            prompt=prompt,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE_SCALE,
            generator=generator,
        ).images[0]
    except Exception as e:
        logger.error(f"Generation failed on device {worker.index}: {e}")
        raise HTTPException(500, f"Generation failed: {e}")
    finally:
        pool.put(worker)  # release the GPU back to the pool

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
