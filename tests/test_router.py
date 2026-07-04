import asyncio
from types import SimpleNamespace

import utils.llm_client as llm
from utils.llm_client import route_message, plan_web_search


def _fake_client(reply_content, raise_error=False):
    async def create(**kwargs):
        if raise_error:
            raise RuntimeError("ollama down")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply_content))]
        )
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def route(monkeypatch, reply, **kw):
    monkeypatch.setattr(llm, "client", _fake_client(reply, **kw))
    return asyncio.run(route_message("любое сообщение"))


def test_remind_intent(monkeypatch):
    assert route(monkeypatch, "REMIND") == ("remind", None)
    assert route(monkeypatch, "remind") == ("remind", None)


def test_search_intent_with_query(monkeypatch):
    assert route(monkeypatch, "SEARCH: погода Томск") == ("search", "погода Томск")
    # legacy pre-router answer format still understood
    assert route(monkeypatch, "YES: курс доллара") == ("search", "курс доллара")


def test_search_without_query_falls_back_to_prompt(monkeypatch):
    action, query = route(monkeypatch, "SEARCH:")
    assert action == "search" and query == "любое сообщение"


def test_plain_chat(monkeypatch):
    assert route(monkeypatch, "NO") == ("none", None)
    assert route(monkeypatch, "какой-то мусор") == ("none", None)


def test_llm_failure_degrades_to_none(monkeypatch):
    assert route(monkeypatch, "", raise_error=True) == ("none", None)


def test_plan_web_search_wrapper(monkeypatch):
    monkeypatch.setattr(llm, "client", _fake_client("SEARCH: новости"))
    assert asyncio.run(plan_web_search("что нового?")) == "новости"
    monkeypatch.setattr(llm, "client", _fake_client("REMIND"))
    assert asyncio.run(plan_web_search("напомни позже")) is None
