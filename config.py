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
