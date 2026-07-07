import asyncio

import utils.reactions as reactions
from utils.reactions import react_seen


class _FakeMessage:
    def __init__(self, fail=False):
        self.reacted = None
        self.fail = fail

    async def react(self, reaction):
        if self.fail:
            raise RuntimeError("reactions disabled in this chat")
        self.reacted = reaction


def test_reacts_when_enabled(monkeypatch):
    monkeypatch.setattr(reactions, "REACT_ON_SEEN", True)
    msg = _FakeMessage()
    asyncio.run(react_seen(msg))
    assert msg.reacted and msg.reacted[0].emoji == "👀"


def test_no_reaction_when_disabled(monkeypatch):
    monkeypatch.setattr(reactions, "REACT_ON_SEEN", False)
    msg = _FakeMessage()
    asyncio.run(react_seen(msg))
    assert msg.reacted is None


def test_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(reactions, "REACT_ON_SEEN", True)
    # a chat where reactions are off must not break the handler
    asyncio.run(react_seen(_FakeMessage(fail=True)))
