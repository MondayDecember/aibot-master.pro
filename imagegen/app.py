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
import threading

import torch
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL_ID = os.getenv("IMAGEGEN_MODEL", "stabilityai/sd-turbo")
STEPS = int(os.getenv("IMAGEGEN_STEPS", "1"))
GUIDANCE_SCALE = float(os.getenv("IMAGEGEN_GUIDANCE_SCALE", "0.0"))
MAX_PROMPT_CHARS = int(os.getenv("IMAGEGEN_MAX_PROMPT_CHARS", "500"))

app = FastAPI(title="aibot-imagegen")

# Loaded lazily on first request (not at import/startup) so `uvicorn app:app`
# comes up instantly - the multi-GB model download/load only happens once
# someone actually asks for an image. A lock serializes generations: the
# GPU can only do one at a time anyway, and DirectML pipelines aren't
# guaranteed thread-safe for concurrent calls.
_pipe = None
_pipe_lock = threading.Lock()


def _load_pipeline():
    global _pipe
    if _pipe is not None:
        return _pipe
    with _pipe_lock:
        if _pipe is None:
            import torch_directml
            from diffusers import AutoPipelineForText2Image

            device = torch_directml.device()
            logger.info(f"Loading '{MODEL_ID}' onto {torch_directml.device_name(0)}...")
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
            _pipe = pipe
            logger.info("Model loaded.")
    return _pipe


class GenerateRequest(BaseModel):
    prompt: str
    seed: int | None = None


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_ID, "loaded": _pipe is not None}


@app.post("/generate")
def generate(req: GenerateRequest):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Empty prompt")
    if len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[:MAX_PROMPT_CHARS]

    pipe = _load_pipeline()
    generator = None
    if req.seed is not None:
        generator = torch.Generator().manual_seed(req.seed)

    try:
        image = pipe(
            prompt=prompt,
            num_inference_steps=STEPS,
            guidance_scale=GUIDANCE_SCALE,
            generator=generator,
        ).images[0]
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(500, f"Generation failed: {e}")

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
