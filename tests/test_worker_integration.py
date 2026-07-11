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
        self.store = {}

    async def blpop(self, key, timeout=0):
        if self.jobs:
            return (key, self.jobs.pop(0))
        raise asyncio.CancelledError  # queue drained - stop the worker loop

    async def rpush(self, key, value):
        self.pushed.append(json.loads(value))
        return len(self.pushed)

    # stop-flag / regen-prompt storage used by the streaming path
    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def delete(self, key):
        self.store.pop(key, None)


class FakeBot:
    def __init__(self):
        self.edits = []
        self.sent = []
        self.documents = []

    async def edit_message_text(self, chat_id=None, message_id=None, text=None, parse_mode=None, reply_markup=None):
        self.edits.append(text)

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent.append(text)

    async def send_document(self, chat_id, document):
        self.documents.append((document.filename, document.data))


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

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
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

    async def fake_generate(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        return "x" * 9000

    bot, _ = _run(monkeypatch, [_job(31338)], generate=fake_generate)

    # first chunk edits the placeholder, the rest arrive as new messages
    final_chunks = [bot.edits[-1]] + bot.sent
    assert all(len(c) <= worker.TELEGRAM_MESSAGE_LIMIT for c in final_chunks)
    assert "".join(final_chunks) == "x" * 9000


def test_long_reply_with_code_sends_code_as_a_file(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31352))

    code = "print('line')\n" * 400  # long enough to push the whole reply past the limit
    reply = "Вот объяснение. " * 300 + f"\n```python\n{code}\n```\n"
    assert len(reply) > worker.TELEGRAM_MESSAGE_LIMIT

    async def fake_generate(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        return reply

    bot, _ = _run(monkeypatch, [_job(31352)], generate=fake_generate)

    assert len(bot.documents) == 1
    filename, data = bot.documents[0]
    assert filename == "snippet.py"
    assert data.decode("utf-8").strip() == code.strip()
    # the code itself isn't repeated in the chat text - just a short note
    all_text = " ".join([bot.edits[-1]] + bot.sent)
    assert "print('line')" not in all_text


def test_llm_failure_shows_error_not_crash(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31339))

    async def broken_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        raise RuntimeError("ollama down")
        yield  # pragma: no cover - makes it an async generator

    bot, _ = _run(monkeypatch, [_job(31339)], stream=broken_stream)

    from utils.texts import t
    assert bot.edits[-1] == t("error_generic")
    # the failed turn must not be persisted
    assert asyncio.run(get_history(31339, limit=10)) == []


def test_regen_prompt_is_stored(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31341))

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        yield "ответ"

    _, redis = _run(monkeypatch, [_job(31341, prompt="как дела?")], stream=fake_stream)
    # the user's prompt is kept so the ↻ button can re-run it
    assert redis.store.get("regen:31341") == "как дела?"


def test_stop_button_cuts_the_stream(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31342))
    # edit (and thus the stop-check) on every delta
    monkeypatch.setattr(worker, "STREAM_EDIT_INTERVAL", 0)
    monkeypatch.setattr(worker.ChatActionSender, "typing", lambda **kw: _noop_typing())
    monkeypatch.setattr(worker, "AUTO_WEB_SEARCH", False)
    monkeypatch.setattr(worker, "STREAM_RESPONSES", True)

    bot, redis = FakeBot(), FakeRedis([_job(31342)])

    # The worker clears any stale stop flag before streaming, so simulate the
    # user tapping Stop mid-stream: set the flag after the first delta.
    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        yield "начало "
        redis.store["stop:1:10"] = "1"
        yield "середина "
        yield "конец"

    monkeypatch.setattr(worker, "stream_response", fake_stream)
    asyncio.run(worker.process_queue(bot, redis))

    from utils.texts import t
    assert t("stopped_note") in bot.edits[-1]
    assert "конец" not in bot.edits[-1]


def test_usersummary_job_sends_summary(monkeypatch):
    asyncio.run(init_db())

    async def fake_summarize(history_id):
        return "• обсудили сервер\n• решили сделать бэкап"

    monkeypatch.setattr(worker, "summarize_history", fake_summarize)
    bot = FakeBot()
    redis = FakeRedis([json.dumps({
        "chat_id": 1, "user_id": 5, "history_id": 5,
        "context_type": "usersummary", "bot_message_id": 10, "prompt": "",
    })])
    asyncio.run(worker.process_queue(bot, redis))
    assert "бэкап" in bot.edits[-1]


def test_custom_prompt_is_applied(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31350))
    from db.database import set_custom_prompt
    asyncio.run(set_custom_prompt(31350, "ВСЕГДА отвечай одним словом"))

    seen = {}

    async def capture_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        seen["system_prompt"] = system_prompt
        yield "ок"

    _run(monkeypatch, [_job(31350)], stream=capture_stream)
    assert "ВСЕГДА отвечай одним словом" in seen["system_prompt"]


def test_usage_is_logged(monkeypatch):
    import time
    from db.database import get_usage_summary, prune_usage
    asyncio.run(init_db())
    asyncio.run(clear_history(31360))
    asyncio.run(prune_usage(int(time.time()) + 1))  # wipe log
    monkeypatch.setattr(worker, "USAGE_STATS", True)

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        if stats is not None:
            stats["prompt_tokens"] = 7
            stats["completion_tokens"] = 3
            stats["total_tokens"] = 10
        yield "ответ"

    _run(monkeypatch, [_job(31360)], stream=fake_stream)
    summary = asyncio.run(get_usage_summary(0))
    assert summary["requests"] == 1 and summary["tokens"] == 10


def test_usage_logs_the_actually_used_model(monkeypatch):
    # stats["model"] is what utils.llm_client._resolve_model() actually used,
    # which can differ from the configured TEXT_MODEL when that model isn't
    # installed on the backend - /usage must record the real one, not the
    # (possibly broken) configured default.
    import time
    from db.database import get_recent_usage, prune_usage
    asyncio.run(init_db())
    asyncio.run(clear_history(31361))
    asyncio.run(prune_usage(int(time.time()) + 1))  # wipe log
    monkeypatch.setattr(worker, "USAGE_STATS", True)

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        if stats is not None:
            stats["model"] = "actually-installed-model"
            stats["prompt_tokens"] = 1
            stats["completion_tokens"] = 1
            stats["total_tokens"] = 2
        yield "ответ"

    _run(monkeypatch, [_job(31361)], stream=fake_stream)
    recent = asyncio.run(get_recent_usage(1))
    assert recent[0]["model"] == "actually-installed-model"


def test_token_footer_shown_and_not_stored(monkeypatch):
    asyncio.run(init_db())
    asyncio.run(clear_history(31351))
    monkeypatch.setattr(worker, "SHOW_TOKENS", True)

    async def fake_stream(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        if stats is not None:
            stats["prompt_tokens"] = 12
            stats["completion_tokens"] = 8
            stats["total_tokens"] = 20
        yield "готово"

    bot, _ = _run(monkeypatch, [_job(31351)], stream=fake_stream)
    # footer appears in the shown reply...
    assert "20" in bot.edits[-1] and "🔢" in bot.edits[-1]
    # ...but the stored history has the clean reply only
    hist = asyncio.run(get_history(31351, limit=10))
    assert hist[-1]["content"] == "готово"


def test_summary_job_queued_after_threshold(monkeypatch):
    # conftest sets SUMMARIZE_EVERY=5; two jobs write 4 rows, then the third
    # crosses the threshold and must enqueue a summarize job
    asyncio.run(init_db())
    asyncio.run(clear_history(31340))

    async def fake_generate(prompt, history_id, context_type, model_override=None, system_prompt=None, stats=None):
        return "ok"

    jobs = [_job(31340) for _ in range(3)]
    _, redis = _run(monkeypatch, jobs, generate=fake_generate)

    summarize_jobs = [j for j in redis.pushed if j.get("context_type") == "summarize"]
    assert summarize_jobs and summarize_jobs[0]["history_id"] == 31340
