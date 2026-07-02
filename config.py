import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# SQLite database file. In docker-compose this is overridden to /app/data/bot_data.db
# so the whole data/ directory can be bind-mounted (mounting a single file breaks
# when it doesn't exist yet - docker silently creates a directory in its place).
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# Automatic web search: before answering, the bot asks the LLM in a separate
# request whether the message needs current data from the web. Smart, but it
# doubles the latency of EVERY text/voice reply. Turn it off to answer roughly
# twice as fast - the explicit /web command keeps working either way.
AUTO_WEB_SEARCH = os.getenv("AUTO_WEB_SEARCH", "true").strip().lower() in ("1", "true", "yes", "on")

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

# Personas selectable in Telegram via /persona - a system prompt prepended to every
# request (text, voice, web search, and photo descriptions). "default" = no persona,
# stock assistant behaviour.
PERSONAS = {
    "default": None,
    "pirate": (
        "You are a swashbuckling pirate captain. Speak with pirate slang and flair "
        "(arr, matey, ye, etc.), but stay genuinely helpful and accurate. "
        "Always reply in the same language the user writes in."
    ),
    "yoda": (
        "You are Yoda from Star Wars. Speak with his inverted sentence structure and "
        "wise, cryptic tone, while still giving correct and genuinely useful answers. "
        "Always reply in the same language the user writes in."
    ),
    "sarcastic": (
        "You are a witty, sarcastic assistant who can't resist a dry joke or a bit of "
        "snark, but always gives a correct and useful answer underneath the attitude. "
        "Always reply in the same language the user writes in."
    ),
    "scientist": (
        "You are a meticulous scientist. Be precise, explain your reasoning, use "
        "technical language when it's warranted, but stay clear and easy to follow. "
        "Always reply in the same language the user writes in."
    ),
}
