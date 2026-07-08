import asyncio
import time

from db.database import (
    init_db, add_usage, get_usage_summary, get_recent_usage, prune_usage,
)


def test_usage_log_summary_and_recent():
    async def scenario():
        await init_db()
        await prune_usage(int(time.time()) + 1)  # clear any prior rows
        await add_usage(1, "llama3", "text", 10, 20, 30)
        await add_usage(2, "qwen2.5:14b", "voice", 5, 15, 20)

        summary = await get_usage_summary(0)  # today_start=0 -> everything counts
        assert summary["requests"] == 2
        assert summary["tokens"] == 50
        assert summary["today_requests"] == 2 and summary["today_tokens"] == 50

        recent = await get_recent_usage(10)
        assert len(recent) == 2
        # newest first
        assert recent[0]["total_tokens"] == 20 and recent[0]["model"] == "qwen2.5:14b"
    asyncio.run(scenario())


def test_usage_prune():
    async def scenario():
        await init_db()
        await prune_usage(int(time.time()) + 1)  # wipe
        await add_usage(1, "m", "text", 1, 1, 2)
        # prune everything older than "now+1h" removes the just-added row
        await prune_usage(int(time.time()) + 3600)
        assert (await get_usage_summary(0))["requests"] == 0
    asyncio.run(scenario())
