from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from db.database import get_user_language
from utils.texts import set_current_language


class LanguageMiddleware(BaseMiddleware):
    """Set t()'s language from the user's stored preference for this update.

    Runs as an inner middleware after access control, so every handler's t()
    calls speak the user's chosen language (falls back to BOT_LANGUAGE).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        set_current_language(await get_user_language(user.id) if user else None)
        return await handler(event, data)
