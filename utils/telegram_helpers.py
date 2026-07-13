import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Message

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_DELAY = 1.5


def is_forwarded(message: Message) -> bool:
    """True if the message was forwarded from somewhere (a channel post, a
    news item, another user's message). forward_origin is the Bot API 7.0+
    field; forward_date is the legacy one - check both for compatibility."""
    return getattr(message, "forward_origin", None) is not None \
        or getattr(message, "forward_date", None) is not None


async def answer_resilient(message: Message, *args, **kwargs) -> Message:
    """message.answer() with a couple of retries on transient network
    failures - observed live: Docker Desktop's Windows/WSL2 network layer
    resetting the bot's outbound connection to api.telegram.org (same
    flakiness class already worked around for Redis, see the socket_keepalive
    comment in main.py). Without this, the whole update is silently lost -
    long polling has already marked it delivered, so a failure sending the
    first reply means the user's message just vanishes: no error, nothing
    queued, indistinguishable from the bot hanging."""
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await message.answer(*args, **kwargs)
        except TelegramNetworkError as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                logger.warning(f"message.answer failed ({e}), retrying ({attempt + 1}/{_MAX_RETRIES})...")
                await asyncio.sleep(_RETRY_DELAY)
    raise last_error
