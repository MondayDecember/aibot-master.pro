"""End-to-end worker pipeline on fakes: queue -> LLM (mocked) -> telegram
(mocked) -> history. Catches wiring bugs that unit tests can't see."""
import asyncio
import json
from contextlib import asynccontextmanager

import task_queue.worker as worker
from db.database import init_db, clear_history, get_history


class FakeRedis:
    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.pushed = []

    async def blpop(self, key, timeout=0):
        if self.jobs:
            return (key, self.jobs.pop(0))
        raise asyncio.CancelledError  # queue drained - stop the worker loop

    async def rpush(self, key, value):
        self.pushed.append(json.loads(value))
        return len(self.pushed)


class FakeBot:
    def __init__(self):
        self.edits = []
        self.sent = []

    async def edit_message_text(self, chat_id=None, message_id=None, text=None, parse_mode=None):
        self.edits.append(text)

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append(text)


@asynccontextmanager
async def _noop_typing(*args, **kwargs):
    yield


def _job(user_id, prompt="привет", **overrides):
    data = {
        "chat_id": 1,
        "user_id": user_id,
        "history_id": user_id,
        "prompt": prompt,
        "history_content": prompt,
        "context_type": "text",
        "bot_message_id": 10,
    }
    data.update(overrides)
    return json.dumps(data)


def _run(monkeypatch, jobs, *, stream=None, generate=None):
    monkeypatch.setattr(worker.ChatActionSender, "typing", lambda **kw: _noop_typing())
    monkeypatch.setattr(worker, "AUTO_WEB_SEARCH", False)
    if stream is not None:
        monkeypatch.setattr(worker, "STREAM_RESPONSES", True)
        monkeypatch.setattr(worker, "stream_response", stream)
    else:
        monkeypatch.setattr(worker, "STREAM_RESPONSES", False)
        monkeypatch.setattr(worker, "generate_response", generate)
    bot, redis = FakeBot(), FakeRedis(jobs)
    asyncio.run(worker.process_queue(bot, redis))
    return bot, redis


def test_streamed_text_job_end_to_end(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31337))

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None):
        for part in ("Привет", ", мир!"):
            yield part

    bot, redis = _run(monkeypatch, [_job(31337)], stream=fake_stream)

    # the final edit is the assembled plain-text reply
    assert bot.edits[-1] == "Привет, мир!"
    # both sides of the turn were persisted
    history = asyncio.run(get_history(31337, limit=10))
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["content"] == "Привет, мир!"
    # 2 messages < SUMMARIZE_EVERY(5) - no summary job queued
    assert redis.pushed == []


def test_long_reply_is_split(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31338))

    async def fake_generate(prompt, history_id, context_type, model_override=None, system_prompt=None):
        return "x" * 9000

    bot, _ = _run(monkeypatch, [_job(31338)], generate=fake_generate)

    # first chunk edits the placeholder, the rest arrive as new messages
    final_chunks = [bot.edits[-1]] + bot.sent
    assert all(len(c) <= worker.TELEGRAM_MESSAGE_LIMIT for c in final_chunks)
    assert "".join(final_chunks) == "x" * 9000


def test_llm_failure_shows_error_not_crash(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31339))

    async def broken_stream(prompt, history_id, context_type, model_override=None, system_prompt=None):
        raise RuntimeError("ollama down")
        yield  # pragma: no cover - makes it an async generator

    bot, _ = _run(monkeypatch, [_job(31339)], stream=broken_stream)

    from utils.texts import t
    assert bot.edits[-1] == t("error_generic")
    # the failed turn must not be persisted
    assert asyncio.run(get_history(31339, limit=10)) == []


def test_summary_job_queued_after_threshold(monkeypatch):
    # conftest sets SUMMARIZE_EVERY=5; two jobs write 4 rows, then the third
    # crosses the threshold and must enqueue a summarize job
    asyncio.run(init_db())
    asyncio.run(clear_history(31340))

    async def fake_generate(prompt, history_id, context_type, model_override=None, system_prompt=None):
        return "ok"

    jobs = [_job(31340) for _ in range(3)]
    _, redis = _run(monkeypatch, jobs, generate=fake_generate)

    summarize_jobs = [j for j in redis.pushed if j.get("context_type") == "summarize"]
    assert summarize_jobs and summarize_jobs[0]["history_id"] == 31340
