import asyncio
import logging
import tempfile
import os
from aiogram import Bot
from faster_whisper import WhisperModel
from config import WHISPER_MODEL
from utils.texts import t

logger = logging.getLogger(__name__)

# Initialize Whisper model (this will load it into memory)
# Using 'cpu' or 'cuda' depending on what's available
# Compute type 'int8' helps with memory
try:
    whisper_model_instance = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    logger.info(f"Whisper model '{WHISPER_MODEL}' loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load Whisper model: {e}")
    whisper_model_instance = None

def _run_transcription(file_path: str) -> str:
    """CPU-bound; must be called via asyncio.to_thread to avoid blocking the event loop."""
    segments, info = whisper_model_instance.transcribe(file_path, beam_size=5)
    return " ".join(segment.text for segment in segments).strip()

async def transcribe_voice(bot: Bot, file_id: str):
    """
    Downloads a voice message (.ogg) from Telegram and transcribes it using
    faster-whisper. Returns (transcription, None) on success or
    (None, user_facing_error) on failure.
    """
    if not whisper_model_instance:
        return None, t("voice_unavailable")

    temp_file_path = None
    try:
        file_info = await bot.get_file(file_id)

        # Create a temporary file to save the OGG audio
        fd, temp_file_path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)

        await bot.download_file(file_info.file_path, temp_file_path)

        # Run the CPU-bound transcription in a worker thread so it doesn't
        # block the event loop (bot polling and the LLM worker share one loop).
        return await asyncio.to_thread(_run_transcription, temp_file_path), None
    except Exception as e:
        logger.error(f"Error transcribing voice: {e}")
        return None, t("voice_error", error=str(e))
    finally:
        # Cleanup temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
