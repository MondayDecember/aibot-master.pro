import json
import logging

from aiogram.types import Message

from config import RATE_LIMIT_PER_MINUTE
from utils.texts import t

logger = logging.getLogger(__name__)


async def _over_rate_limit(redis, user_id: int) -> bool:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return False
    key = f"rate:{user_id}"
    count = await redis.incr(key)
    if count == 1:
        # first request of the window starts the 60s clock
        await redis.expire(key, 60)
    return count > RATE_LIMIT_PER_MINUTE


async def enqueue_llm_job(
    redis,
    message: Message,
    bot_message: Message,
    prompt,
    history_content: str,
    context_type: str,
) -> bool:
    """
    Single entry point for queueing LLM work: enforces the per-user rate
    limit and shows the queue position when the worker is busy.
    Returns False (and tells the user) when the rate limit was hit.
    """
    user_id = message.from_user.id
    if await _over_rate_limit(redis, user_id):
        logger.info(f"Rate limit hit by user {user_id}")
        await bot_message.edit_text(
            t("rate_limited", limit=RATE_LIMIT_PER_MINUTE), parse_mode=None
        )
        return False

    job_data = {
        "chat_id": message.chat.id,
        "user_id": user_id,
        "prompt": prompt,
        "history_content": history_content,
        "context_type": context_type,
        "bot_message_id": bot_message.message_id,
    }
    # rpush returns the queue length including this job
    queue_len = await redis.rpush("llm_queue", json.dumps(job_data))
    if queue_len > 1:
        try:
            await bot_message.edit_text(t("queue_position", n=queue_len), parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Queue position edit failed: {e}")
    return True
