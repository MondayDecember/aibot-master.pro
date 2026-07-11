"""answer_resilient() retries message.answer() on transient network errors -
observed live: Docker Desktop's Windows/WSL2 network layer resetting the
bot's outbound connection to api.telegram.org, which silently dropped the
whole update (long polling had already marked it delivered) with no reply
and nothing queued - looked exactly like the bot hanging."""
import asyncio

import pytest
from aiogram.exceptions import TelegramNetworkError

from utils.telegram_helpers import answer_resilient


class _FakeMessage:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times
        self.calls = 0

    async def answer(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TelegramNetworkError(method=None, message="boom")
        return "sent"


def test_succeeds_immediately_when_no_error():
    msg = _FakeMessage(fail_times=0)
    result = asyncio.run(answer_resilient(msg, "hello"))
    assert result == "sent"
    assert msg.calls == 1


def test_retries_and_eventually_succeeds(monkeypatch):
    monkeypatch.setattr("utils.telegram_helpers._RETRY_DELAY", 0)
    msg = _FakeMessage(fail_times=2)
    result = asyncio.run(answer_resilient(msg, "hello"))
    assert result == "sent"
    assert msg.calls == 3


def test_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("utils.telegram_helpers._RETRY_DELAY", 0)
    msg = _FakeMessage(fail_times=99)
    with pytest.raises(TelegramNetworkError):
        asyncio.run(answer_resilient(msg, "hello"))
    # initial attempt + _MAX_RETRIES retries
    from utils.telegram_helpers import _MAX_RETRIES
    assert msg.calls == _MAX_RETRIES + 1
