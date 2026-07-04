"""Helpers that work against any OpenAI-compatible local LLM server - not
just Ollama. Also tested against LM Studio's built-in server (Settings ->
Developer -> enable "Local Server", OpenAI-compatible by design on port
1234 by default). Point OLLAMA_API_BASE at whichever one you're running;
the name is historical, the code underneath was never Ollama-specific for
chat completions and now isn't for model listing either.
"""
import logging

from utils.llm_client import client

logger = logging.getLogger(__name__)


async def list_installed_models() -> list[str]:
    """
    Model names currently available on the configured backend, or [] if
    it's unreachable. Uses the standard OpenAI /v1/models endpoint (which
    Ollama, LM Studio, vLLM, LocalAI, etc. all implement) instead of any
    backend-specific API, so this works the same regardless of which one
    OLLAMA_API_BASE actually points at.
    """
    try:
        response = await client.models.list()
    except Exception as e:
        logger.warning(f"Could not list models from the LLM backend: {e}")
        return []
    return [m.id for m in response.data if m.id]
