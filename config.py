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

# Stream replies: edit the telegram message progressively while the LLM is
# still generating (ChatGPT-style). Purely cosmetic - turn off if your
# telegram connection is rate-limited.
STREAM_RESPONSES = os.getenv("STREAM_RESPONSES", "true").strip().lower() in ("1", "true", "yes", "on")

# Seconds between streaming edits of the growing reply. Telegram throttles
# message edits (~1/sec per chat is the safe floor) - going lower makes the
# stream smoother but risks flood-wait pauses that freeze it entirely.
STREAM_EDIT_INTERVAL = float(os.getenv("STREAM_EDIT_INTERVAL", "1.0"))

# React with 👀 to a message the moment the bot picks it up - a subtle "seen,
# working on it" indicator. Purely cosmetic; some clients/groups disable
# reactions, in which case it silently does nothing.
REACT_ON_SEEN = os.getenv("REACT_ON_SEEN", "true").strip().lower() in ("1", "true", "yes", "on")

# Access control: comma-separated telegram user IDs allowed to use the bot.
# Empty = the bot answers everyone. Rejected users are shown their ID so the
# owner can add them.
def _parse_allowed_ids(raw: str) -> list:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and int(part) not in ids:
            ids.append(int(part))
    return ids

_allowed_list = _parse_allowed_ids(os.getenv("ALLOWED_USER_IDS", ""))
ALLOWED_USER_IDS = frozenset(_allowed_list)

# Admin for /stats: explicit ADMIN_USER_ID, or the first entry of
# ALLOWED_USER_IDS. None = /stats is disabled.
_admin_raw = os.getenv("ADMIN_USER_ID", "").strip()
ADMIN_USER_ID = int(_admin_raw) if _admin_raw.isdigit() else (_allowed_list[0] if _allowed_list else None)

# Language of the bot's own interface messages ("en" or "ru"). Model replies
# are always in whatever language the user writes in.
BOT_LANGUAGE = os.getenv("BOT_LANGUAGE", "en").strip().lower()

# Search engine for web search: a SearXNG instance (self-hosted, no rate
# limits) if you have one, e.g. http://192.168.1.1:8080/search - needs
# `formats: [html, json]` in SearXNG's settings.yml, JSON is disabled by
# default. Empty = use the DDGS metasearch library (DuckDuckGo and others,
# no setup needed but can get rate-limited under heavy use).
SEARXNG_URL = os.getenv("SEARXNG_URL", "").strip()

# Deep web search: after a search the bot OPENS the top N result pages and
# reads their text, instead of answering from the ~300-char search snippets
# alone. 0 = snippets only (old behaviour). More pages / more chars = better
# answers but a larger prompt: make sure the model's context window can take
# it (2 pages x 2000 chars is safe for the default 4k window).
WEB_FETCH_PAGES = int(os.getenv("WEB_FETCH_PAGES", "2"))
WEB_PAGE_MAX_CHARS = int(os.getenv("WEB_PAGE_MAX_CHARS", "2000"))
# Hard cap on the *total* assembled web-search block (all pages/snippets
# combined) regardless of how the two settings above are tuned - the real
# safety net against blowing past the model's context window. Only raise
# this together with MODEL_NUM_CTX: 2500 chars is safe on Ollama's default
# ~4k-token context; an 8000 cap needs roughly an 8k+ token MODEL_NUM_CTX or
# you'll get a 400 "exceeds context size" error.
WEB_CONTEXT_MAX_CHARS = int(os.getenv("WEB_CONTEXT_MAX_CHARS", "2500"))

# Anti-spam: how many LLM requests one user may queue per minute (0 = off).
# Commands like /clear or /model are not counted - only messages that cost
# LLM time (text, voice, photos, documents, /web).
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

# Group chatter: let the bot occasionally join the group conversation on its
# own, like a regular member. GROUP_CHATTINESS is the percent chance (0-100)
# to react to any given group message it wasn't addressed in; 0 = off. The
# cooldown guarantees at most one spontaneous remark per chat per interval,
# no matter how lively the chat is.
GROUP_CHATTINESS = int(os.getenv("GROUP_CHATTINESS", "0"))
GROUP_CHATTER_COOLDOWN = int(os.getenv("GROUP_CHATTER_COOLDOWN", "300"))

# How many characters of an uploaded document are passed to the LLM. Local
# models have small context windows (llama3: 8k tokens), so keep this modest.
DOC_MAX_CHARS = int(os.getenv("DOC_MAX_CHARS", "12000"))

# How many past messages (user + bot combined) are given to the LLM as
# conversation memory. Full history is stored in SQLite forever - this only
# limits what fits into the model's context window. Higher = better memory
# but slower replies and more RAM on small models.
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "10"))

# Database backups: every BACKUP_INTERVAL_HOURS a consistent snapshot of the
# SQLite db is written to <data dir>/backups/, keeping the newest BACKUP_KEEP
# files. Set BACKUP_INTERVAL_HOURS=0 to disable.
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_KEEP = int(os.getenv("BACKUP_KEEP", "7"))

# Long-term memory: every SUMMARIZE_EVERY new messages the bot asks the LLM
# to fold older conversation into a compact summary (max SUMMARY_MAX_CHARS),
# which is then prepended to every request. This lets the bot "remember"
# things beyond the HISTORY_LIMIT window at the cost of one extra LLM call
# per SUMMARIZE_EVERY messages (queued, so it never delays user replies).
LONG_TERM_MEMORY = os.getenv("LONG_TERM_MEMORY", "true").strip().lower() in ("1", "true", "yes", "on")
SUMMARIZE_EVERY = int(os.getenv("SUMMARIZE_EVERY", "20"))
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "1500"))

# Model for memory summaries and reminder parsing. Empty = the main
# TEXT_MODEL. A small model (e.g. llama3.2:3b) makes background archiving
# much faster and avoids swapping the big model out of RAM for it.
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "").strip()

# Timezone for reminders and the bot's sense of "now" (IANA name like
# Europe/Moscow). The LLM has no clock - the bot tells it the current date
# and time with every request, in this timezone.
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
try:
    from zoneinfo import ZoneInfo
    TZINFO = ZoneInfo(TIMEZONE)
except Exception:
    from datetime import timezone as _tz_fallback
    TZINFO = _tz_fallback.utc

TEXT_MODEL = os.getenv("TEXT_MODEL", "llama3")
VISION_MODEL = os.getenv("VISION_MODEL", "llama3.2-vision")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# OCR: pull text off a photo with Tesseract (CPU, bundled in the image) before
# it goes to the vision model, so screenshots / documents / error messages are
# read reliably. OCR_LANGUAGES is a Tesseract lang string ("rus+eng").
OCR_ENABLED = os.getenv("OCR_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "rus+eng").strip() or "rus+eng"

# Model context window in tokens. Ollama defaults to a small 2048/4096 window
# and silently truncates older messages - raising this is the real "memory"
# knob (HISTORY_LIMIT only controls how many messages the bot SENDS). Passed
# to the backend as an option; 0 = don't send (use the model's own default).
# Bigger = remembers more but uses more RAM/VRAM.
MODEL_NUM_CTX = int(os.getenv("MODEL_NUM_CTX", "0"))

# Show a "🔢 tokens" footer under replies (prompt+completion). Off by default.
SHOW_TOKENS = os.getenv("SHOW_TOKENS", "false").strip().lower() in ("1", "true", "yes", "on")

# Log every LLM reply (time, user, model, token counts) to the database so the
# admin can review usage with /usage. Independent of SHOW_TOKENS.
USAGE_STATS = os.getenv("USAGE_STATS", "true").strip().lower() in ("1", "true", "yes", "on")
# Prune usage-log rows older than this many days (0 = keep forever).
USAGE_RETENTION_DAYS = int(os.getenv("USAGE_RETENTION_DAYS", "90"))

# Voice replies: when a user sends a voice message, also reply with a
# synthesized voice note (in addition to the text reply), using a local
# neural TTS model (Piper - CPU-only, no GPU needed, ~0.2s per sentence).
VOICE_REPLIES = os.getenv("VOICE_REPLIES", "true").strip().lower() in ("1", "true", "yes", "on")
_default_tts_voice = "ru_RU-dmitri-medium" if BOT_LANGUAGE == "ru" else "en_US-lessac-medium"
TTS_VOICE = os.getenv("TTS_VOICE", _default_tts_voice)
# Downloaded once and cached here - point this at the persistent /app/data
# volume in docker-compose so it survives container recreation.
TTS_VOICE_DIR = os.getenv("TTS_VOICE_DIR", "tts_voices")
# Cap how much text gets synthesized - a multi-paragraph reply would take a
# while to speak and produce an awkwardly long voice note.
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", "1000"))

# Image generation (/imagine): talks to the separate service in imagegen/,
# which must be started manually (it runs natively on the host - see
# imagegen/README.md for why it can't just be another docker-compose
# service). Off by default since most installs won't have it running.
IMAGEGEN_ENABLED = os.getenv("IMAGEGEN_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
IMAGEGEN_API_BASE = os.getenv("IMAGEGEN_API_BASE", "http://host.docker.internal:7861")
# Shared secret between the bot and the imagegen service. The service binds
# 0.0.0.0 (host.docker.internal needs it), so without a key anyone on the
# same network could POST /generate and burn the GPU. Must match the value
# in imagegen/.env. Empty = no auth (only safe on an isolated host).
IMAGEGEN_API_KEY = os.getenv("IMAGEGEN_API_KEY", "").strip()

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

# Always-on formatting/style instruction, regardless of persona. Without it,
# local models default to writing Markdown-heavy "wiki article" answers
# (headers, tables, horizontal rules) - Telegram messages are sent as plain
# text, so that markup just shows up as literal #, ---, |, ** clutter instead
# of being rendered.
BASE_SYSTEM_PROMPT = (
    "You are chatting with the user in a Telegram messenger conversation, not "
    "writing a document. Reply in plain, natural conversational sentences. "
    "Do not use Markdown headers (#, ##), horizontal rules (---), tables "
    "(pipes |), or blockquotes (>) - Telegram shows them as literal symbols, "
    "not formatting. Match the depth of the answer to the question: greetings "
    "and small talk deserve a line or two, but substantive questions deserve a "
    "complete, generous answer - explain, give details, reasons and examples, "
    "don't cut the explanation short. "
    "You DO have a built-in reminders feature: if the user asks to be "
    "reminded of something or to set a note/alarm, never claim you can't - "
    "tell them to phrase it as \"напомни <когда> <что>\" (e.g. \"напомни "
    "завтра в 15:00 позвонить врачу\") or use the /remind command, and the "
    "bot will deliver a notification at that time. "
    "When you write code, add brief comments for non-obvious parts directly "
    "in the code itself, not only explained afterward in prose - someone "
    "reading just the code block should be able to follow it. "
    "Always reply in the same language the user writes in."
)

def build_system_prompt(persona_key: str) -> str:
    """Combine the base formatting/style instruction with the chosen persona's flavor text."""
    flavor = PERSONAS.get(persona_key)
    return f"{BASE_SYSTEM_PROMPT} {flavor}" if flavor else BASE_SYSTEM_PROMPT

# Personas selectable in Telegram via /persona - flavor text added on top of
# BASE_SYSTEM_PROMPT for every request (text, voice, web search, and photo
# descriptions). "default" = no extra flavor, just the base style above.
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
    "coder": (
        "You are a senior software engineer. Give professional, production-quality "
        "answers: put code in triple-backtick ``` fenced blocks, add clear comments "
        "explaining non-obvious parts, follow the language's idioms and best "
        "practices, and briefly note edge cases, errors to handle, and security or "
        "performance concerns when relevant. Prefer correct, complete, runnable code "
        "over hand-waving. Keep prose around the code concise. "
        "Always reply in the same language the user writes in."
    ),
}
