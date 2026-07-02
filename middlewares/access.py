import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import ALLOWED_USER_IDS

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Reject updates from users not in ALLOWED_USER_IDS.

    An empty ALLOWED_USER_IDS means the bot is open to everyone. Rejected
    users get a message with their telegram ID so the owner can add them
    to the list in .env.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not ALLOWED_USER_IDS:
            return await handler(event, data)
        user = data.get("event_from_user")
        if user and user.id in ALLOWED_USER_IDS:
            return await handler(event, data)

        user_id = user.id if user else "unknown"
        logger.info(f"Rejected update from unauthorized user {user_id}")
        if isinstance(event, CallbackQuery):
            await event.answer("Access denied.", show_alert=True)
        elif isinstance(event, Message):
            await event.answer(
                f"Access denied. Your Telegram ID: {user_id}\n"
                "Ask the bot owner to add it to ALLOWED_USER_IDS in .env."
            )
        return None
