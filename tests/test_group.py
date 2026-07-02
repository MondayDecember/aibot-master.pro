import asyncio
from types import SimpleNamespace

from utils.group import gate_group_message, history_key


class FakeBot:
    async def me(self):
        return SimpleNamespace(id=999, username="MyTestBot")


def msg(chat_type, reply_from=None, uid=42, chat_id=-100):
    reply = SimpleNamespace(from_user=SimpleNamespace(id=reply_from)) if reply_from else None
    return SimpleNamespace(
        chat=SimpleNamespace(type=chat_type, id=chat_id),
        from_user=SimpleNamespace(id=uid),
        bot=FakeBot(),
        reply_to_message=reply,
    )


def gate(message, text):
    return asyncio.run(gate_group_message(message, text))


def test_private_always_passes():
    assert gate(msg("private"), "hi") == (True, "hi")


def test_group_plain_message_ignored():
    ok, _ = gate(msg("supergroup"), "просто болтаем")
    assert not ok


def test_group_mention_stripped_case_insensitive():
    ok, cleaned = gate(msg("supergroup"), "@mytestbot привет, как дела?")
    assert ok and cleaned == "привет, как дела?"


def test_group_reply_to_bot_passes():
    ok, _ = gate(msg("supergroup", reply_from=999), "ответ боту")
    assert ok


def test_group_reply_to_human_ignored():
    ok, _ = gate(msg("supergroup", reply_from=123), "ответ человеку")
    assert not ok


def test_bare_mention_passes_with_empty_text():
    ok, cleaned = gate(msg("supergroup"), "@MyTestBot")
    assert ok and cleaned is None


def test_history_key_private_vs_group():
    assert history_key(msg("private", uid=42)) == 42
    assert history_key(msg("supergroup", chat_id=-100500)) == -100500
