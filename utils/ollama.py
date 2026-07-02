"""Shared helpers for talking to Ollama's native API (not the OpenAI-
compatible /v1 endpoint used for chat completions)."""
import logging
import aiohttp
from config import OLLAMA_API_BASE

logger = logging.getLogger(__name__)

def _native_api_base() -> str:
    # OLLAMA_API_BASE points at the OpenAI-compatible endpoint (".../v1"),
    # the native API (model list, etc.) lives one level up.
    base = OLLAMA_API_BASE.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base

async def list_installed_models() -> list[str]:
    """Names of models currently pulled in Ollama, or [] if it's unreachable."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{_native_api_base()}/api/tags") as resp:
                data = await resp.json()
    except Exception as e:
        logger.warning(f"Could not list Ollama models: {e}")
        return []
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
