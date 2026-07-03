import asyncio
import logging
import os
import tempfile
import wave
from pathlib import Path

from config import TTS_VOICE, TTS_VOICE_DIR, TTS_MAX_CHARS, VOICE_REPLIES

logger = logging.getLogger(__name__)

# Loaded once at import time (same pattern as the Whisper STT model in
# voice_helper.py) - skipped entirely when VOICE_REPLIES is off, so
# disabling the feature also avoids the first-run model download.
voice_instance = None
if VOICE_REPLIES:
    try:
        from piper.voice import PiperVoice
        from piper.download_voices import download_voice

        Path(TTS_VOICE_DIR).mkdir(parents=True, exist_ok=True)
        model_path = os.path.join(TTS_VOICE_DIR, f"{TTS_VOICE}.onnx")
        config_path = f"{model_path}.json"
        if not os.path.exists(model_path):
            download_voice(TTS_VOICE, Path(TTS_VOICE_DIR))
        voice_instance = PiperVoice.load(model_path, config_path)
        logger.info(f"TTS voice '{TTS_VOICE}' loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load TTS voice '{TTS_VOICE}': {e}")
        voice_instance = None


def _run_synthesis(text: str, wav_path: str):
    """CPU-bound; must be called via asyncio.to_thread to avoid blocking the event loop."""
    with wave.open(wav_path, "wb") as wav_file:
        voice_instance.synthesize_wav(text, wav_file)


async def synthesize_speech(text: str) -> bytes | None:
    """
    Synthesize `text` into a Telegram-ready OGG/Opus voice note (Piper
    writes WAV; ffmpeg - already a dependency for Whisper - converts it).
    Returns None on any failure (voice not loaded, empty text, ffmpeg
    missing, conversion error). Callers should treat that as "skip the
    voice reply" rather than an error - the text reply has already been
    sent by the time this runs.
    """
    if not voice_instance:
        return None
    text = text.strip()
    if not text:
        return None
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS].rstrip() + "…"

    wav_path = None
    ogg_path = None
    try:
        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        await asyncio.to_thread(_run_synthesis, text, wav_path)

        fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", wav_path, "-c:a", "libopus", "-b:a", "32k", ogg_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if proc.returncode != 0:
            logger.warning(f"ffmpeg failed to convert TTS audio (exit code {proc.returncode})")
            return None

        with open(ogg_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"TTS synthesis failed: {e}")
        return None
    finally:
        for path in (wav_path, ogg_path):
            if path and os.path.exists(path):
                os.remove(path)
