"""utils.tts_helper.synthesize_speech, with the real Piper model and ffmpeg
mocked out - CI has no voice model downloaded and no guaranteed ffmpeg."""
import asyncio

import pytest

import utils.tts_helper as tts_helper


class _FakeProc:
    def __init__(self, returncode=0):
        self.returncode = returncode

    async def wait(self):
        return self.returncode


@pytest.mark.asyncio
async def test_no_voice_loaded_returns_none(monkeypatch):
    monkeypatch.setattr(tts_helper, "voice_instance", None)
    assert await tts_helper.synthesize_speech("hello") is None


@pytest.mark.asyncio
async def test_empty_text_returns_none(monkeypatch):
    monkeypatch.setattr(tts_helper, "voice_instance", object())
    assert await tts_helper.synthesize_speech("   ") is None


@pytest.mark.asyncio
async def test_truncates_long_text_before_synthesis(monkeypatch):
    monkeypatch.setattr(tts_helper, "voice_instance", object())
    monkeypatch.setattr(tts_helper, "TTS_MAX_CHARS", 10)

    seen = {}

    def fake_run_synthesis(text, wav_path):
        seen["text"] = text
        open(wav_path, "wb").close()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProc(returncode=0)

    monkeypatch.setattr(tts_helper, "_run_synthesis", fake_run_synthesis)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await tts_helper.synthesize_speech("x" * 50)

    assert seen["text"] == "x" * 10 + "…"
    assert result == b""  # ogg temp file was left empty by the fake ffmpeg step


@pytest.mark.asyncio
async def test_ffmpeg_failure_returns_none(monkeypatch):
    monkeypatch.setattr(tts_helper, "voice_instance", object())
    monkeypatch.setattr(tts_helper, "_run_synthesis", lambda text, wav_path: open(wav_path, "wb").close())

    async def failing_subprocess_exec(*args, **kwargs):
        return _FakeProc(returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", failing_subprocess_exec)

    assert await tts_helper.synthesize_speech("hello") is None
