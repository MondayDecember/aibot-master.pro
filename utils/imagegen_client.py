"""Client for the local image-generation service (see imagegen/README.md).
That service runs natively on the host - this just talks HTTP to it, the
same way llm_client.py talks to Ollama."""
import logging

import aiohttp

from config import IMAGEGEN_API_BASE

logger = logging.getLogger(__name__)


async def generate_image(prompt: str) -> bytes | None:
    """
    POST prompt to the imagegen service and return PNG bytes, or None if
    the service is unreachable, not running, or generation failed. First
    request after the service starts can be slow (multi-GB model load) -
    give it a generous timeout rather than fail fast.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{IMAGEGEN_API_BASE}/generate", json={"prompt": prompt}
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"Image generation failed ({resp.status}): {body[:300]}")
                    return None
                return await resp.read()
    except Exception as e:
        logger.warning(f"Could not reach image generation service: {e}")
        return None
