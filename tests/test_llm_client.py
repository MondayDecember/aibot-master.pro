"""_resolve_model() falls back to an actually-installed model when the
configured TEXT_MODEL/VISION_MODEL/SUMMARY_MODEL isn't available, instead of
letting every request to the LLM backend fail."""
import asyncio

import utils.llm_client as llm_client


def _patch_installed(monkeypatch, names):
    async def fake_list_installed_models():
        return names
    monkeypatch.setattr("utils.llm_backend.list_installed_models", fake_list_installed_models)


def test_passes_through_when_model_is_installed(monkeypatch):
    _patch_installed(monkeypatch, ["llama3", "qwen2.5vl:7b"])
    assert asyncio.run(llm_client._resolve_model("llama3")) == "llama3"


def test_passes_through_on_base_name_match(monkeypatch):
    # Requested "qwen2.5" (no tag) is left as-is when an installed model
    # shares its base name ("qwen2.5:14b") - same tag-stripped comparison
    # main.py's startup check already uses, not rewritten to the full tag.
    _patch_installed(monkeypatch, ["qwen2.5:14b"])
    assert asyncio.run(llm_client._resolve_model("qwen2.5")) == "qwen2.5"


def test_falls_back_to_first_installed_when_missing(monkeypatch):
    _patch_installed(monkeypatch, ["gpt-oss-20b", "gemma-4-12b"])
    assert asyncio.run(llm_client._resolve_model("qwen2.5:32b")) == "gpt-oss-20b"


def test_passes_through_unchanged_when_backend_unreachable(monkeypatch):
    _patch_installed(monkeypatch, [])
    assert asyncio.run(llm_client._resolve_model("qwen2.5:32b")) == "qwen2.5:32b"
