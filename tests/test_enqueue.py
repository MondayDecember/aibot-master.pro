import asyncio

from task_queue.enqueue import _over_rate_limit


class FakeRedis:
    """Minimal in-memory stand-in for the redis commands the limiter uses."""

    def __init__(self, lose_expire=False):
        self.counters = {}
        self.ttls = {}
        self.lose_expire = lose_expire
        self.expire_calls = 0

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def ttl(self, key):
        return self.ttls.get(key, -1)

    async def expire(self, key, seconds):
        self.expire_calls += 1
        if not self.lose_expire:
            self.ttls[key] = seconds


def test_limit_kicks_in_after_threshold(monkeypatch):
    monkeypatch.setattr("task_queue.enqueue.RATE_LIMIT_PER_MINUTE", 3)
    redis = FakeRedis()
    results = [asyncio.run(_over_rate_limit(redis, 42)) for _ in range(5)]
    assert results == [False, False, False, True, True]


def test_zero_limit_disables(monkeypatch):
    monkeypatch.setattr("task_queue.enqueue.RATE_LIMIT_PER_MINUTE", 0)
    redis = FakeRedis()
    assert not any(asyncio.run(_over_rate_limit(redis, 42)) for _ in range(20))


def test_lost_expire_is_self_healed(monkeypatch):
    # If the first expire never landed (redis hiccup), the ttl stays -1 and
    # the limiter must keep trying to arm it instead of locking the user out
    monkeypatch.setattr("task_queue.enqueue.RATE_LIMIT_PER_MINUTE", 10)
    redis = FakeRedis(lose_expire=True)
    for _ in range(3):
        asyncio.run(_over_rate_limit(redis, 42))
    assert redis.expire_calls == 3  # re-armed on every call while ttl < 0
