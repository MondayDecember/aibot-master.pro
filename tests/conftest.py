import os
import sys
import tempfile

# Make the project root importable and point the app at a throwaway database
# BEFORE any test module imports config (conftest runs first).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="aibot-tests-")
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "test_bot.db"))
os.environ.setdefault("SUMMARIZE_EVERY", "5")
os.environ.setdefault("BACKUP_KEEP", "3")
os.environ.setdefault("BACKUP_INTERVAL_HOURS", "0")
# Importing task_queue.worker pulls in utils.tts_helper, which downloads a
# voice model at import time when VOICE_REPLIES is on - keep tests offline.
os.environ.setdefault("VOICE_REPLIES", "false")
