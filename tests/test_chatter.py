import asyncio

from utils import group


class FakeRedis:
    """Tracks SET NX EX semantics for the chatter cooldown."""

    def __init__(self):
        self.keys = set()

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


def chime(redis):
    return asyncio.run(group.should_chime_in(redis, -100))


def test_disabled_by_default(monkeypatch):
    monkeypatch.setattr(group, "GROUP_CHATTINESS", 0)
    monkeypatch.setattr(group.random, "random", lambda: 0.0)
    assert not chime(FakeRedis())


def test_probability_gate(monkeypatch):
    monkeypatch.setattr(group, "GROUP_CHATTINESS", 10)
    # roll above the threshold -> stays quiet
    monkeypatch.setattr(group.random, "random", lambda: 0.5)
    assert not chime(FakeRedis())
    # roll below the threshold -> speaks
    monkeypatch.setattr(group.random, "random", lambda: 0.05)
    assert chime(FakeRedis())


def test_cooldown_allows_only_one(monkeypatch):
    monkeypatch.setattr(group, "GROUP_CHATTINESS", 100)
    monkeypatch.setattr(group.random, "random", lambda: 0.0)
    redis = FakeRedis()
    assert chime(redis)          # first remark goes through
    assert not chime(redis)      # cooldown key already held
    assert not chime(redis)
