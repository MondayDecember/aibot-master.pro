import os
import sys
import tempfile

import pytest

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


@pytest.fixture(autouse=True)
def _no_real_llm_backend_calls(request, monkeypatch):
    """utils.llm_client._resolve_model() calls list_installed_models() to
    fall back when a configured model isn't installed - a real network call
    otherwise, which made LLM-mocked tests slow/flaky since they only mock
    client.chat.completions.create, not the model-listing call. Default to
    "backend unreachable" (empty list) so _resolve_model is a no-op
    passthrough everywhere; skipped for test_llm_backend/test_llm_client,
    which test list_installed_models()/_resolve_model() themselves and
    supply their own mocks."""
    if request.module.__name__ in ("test_llm_backend", "test_llm_client"):
        return
    async def _fake_list_installed_models():
        return []
    monkeypatch.setattr("utils.llm_backend.list_installed_models", _fake_list_installed_models)
