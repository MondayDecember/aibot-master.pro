import asyncio

from db.database import (
    init_db, add_message, get_history, clear_history, get_stats,
    get_memory, set_memory, count_messages,
    get_user_model, set_user_model,
)
from utils.memory import needs_summary


def test_history_roundtrip():
    async def scenario():
        await init_db()
        await add_message(1, "user", "привет")
        await add_message(1, "assistant", "здравствуйте")
        history = await get_history(1, limit=10)
        assert [m["role"] for m in history] == ["user", "assistant"]
        assert history[0]["content"] == "привет"
        await clear_history(1)
        assert await get_history(1, limit=10) == []
    asyncio.run(scenario())


def test_stats_counts_users_and_messages():
    async def scenario():
        await init_db()
        await clear_history(10)
        await clear_history(20)
        for i in range(3):
            await add_message(10, "user", f"m{i}")
        await add_message(20, "user", "hi")
        stats = await get_stats()
        assert stats["users"] >= 2
        assert stats["messages"] >= 4
    asyncio.run(scenario())


def test_user_settings_upsert():
    async def scenario():
        await init_db()
        await set_user_model(5, "llama3")
        await set_user_model(5, "qwen3")
        assert await get_user_model(5) == "qwen3"
    asyncio.run(scenario())


def test_memory_threshold_lifecycle():
    # conftest sets SUMMARIZE_EVERY=5
    async def scenario():
        await init_db()
        await clear_history(777)
        assert await get_memory(777) == (None, 0)
        assert not await needs_summary(777)
        for i in range(5):
            await add_message(777, "user", f"m{i}")
        assert await needs_summary(777)
        await set_memory(777, "выжимка", await count_messages(777))
        assert not await needs_summary(777)
        summary, _ = await get_memory(777)
        assert summary == "выжимка"
    asyncio.run(scenario())
