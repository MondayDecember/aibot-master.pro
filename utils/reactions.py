import logging

from aiogram.types import Message, ReactionTypeEmoji

from config import REACT_ON_SEEN

logger = logging.getLogger(__name__)


async def react_seen(message: Message):
    """Put a 👀 reaction on a message the bot is about to work on.

    Best-effort: reactions can be disabled in a group, unsupported by an old
    client, or rate-limited - none of that should affect the reply.
    """
    if not REACT_ON_SEEN:
        return
    try:
        await message.react([ReactionTypeEmoji(emoji="👀")])
    except Exception as e:
        logger.debug(f"Reaction failed: {e}")
