import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

TEXT_MODEL = os.getenv("TEXT_MODEL", "llama3")
VISION_MODEL = os.getenv("VISION_MODEL", "llama3.2-vision")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# Models selectable in Telegram via /model, e.g.:
# MODEL_CHOICES=default=qwen2.5vl:7b,coder=qwen3-coder:30b,uncensored=hf.co/OBLITERATUS/Gemma-4-12B-OBLITERATED:Q4_K_M
# Falls back to just TEXT_MODEL as "default" if not set. Only affects text/voice/web_search
# replies - photo analysis always uses VISION_MODEL, regardless of the user's /model choice.
def _parse_model_choices(raw: str) -> dict:
    choices = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        key, _, model_name = pair.partition("=")
        key, model_name = key.strip(), model_name.strip()
        if key and model_name:
            choices[key] = model_name
    return choices

AVAILABLE_MODELS = _parse_model_choices(os.getenv("MODEL_CHOICES", "")) or {"default": TEXT_MODEL}
