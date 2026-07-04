"""list_installed_models() must work against any OpenAI-compatible server
(Ollama, LM Studio, vLLM, ...) via the standard /v1/models endpoint, not
just Ollama's own API."""
import asyncio
from types import SimpleNamespace

import utils.llm_backend as llm_backend


def test_returns_model_ids_from_openai_style_response(monkeypatch):
    response = SimpleNamespace(data=[
        SimpleNamespace(id="llama3"),
        SimpleNamespace(id="qwen2.5vl:7b"),
    ])

    async def fake_list():
        return response

    monkeypatch.setattr(llm_backend.client.models, "list", fake_list)

    result = asyncio.run(llm_backend.list_installed_models())
    assert result == ["llama3", "qwen2.5vl:7b"]


def test_returns_empty_list_when_backend_unreachable(monkeypatch):
    async def failing_list():
        raise ConnectionError("no server running")

    monkeypatch.setattr(llm_backend.client.models, "list", failing_list)

    result = asyncio.run(llm_backend.list_installed_models())
    assert result == []


def test_skips_entries_without_an_id(monkeypatch):
    response = SimpleNamespace(data=[
        SimpleNamespace(id="real-model"),
        SimpleNamespace(id=""),
        SimpleNamespace(id=None),
    ])

    async def fake_list():
        return response

    monkeypatch.setattr(llm_backend.client.models, "list", fake_list)

    result = asyncio.run(llm_backend.list_installed_models())
    assert result == ["real-model"]
