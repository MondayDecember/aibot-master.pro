import re

from aiogram.types import Message


def history_key(message: Message) -> int:
    """Private chats keep per-user history; groups share one history per chat."""
    return message.from_user.id if message.chat.type == "private" else message.chat.id


async def gate_group_message(message: Message, text):
    """
    Decide whether the bot should react to a message.

    Private chats always pass. In groups the bot reacts only when it is
    @mentioned (the mention is stripped from the returned text) or when the
    message is a reply to one of the bot's own messages. Everything else is
    silently ignored so the bot doesn't answer every group message.

    Returns (should_handle, cleaned_text).
    """
    if message.chat.type == "private":
        return True, text

    me = await message.bot.me()
    if (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == me.id
    ):
        return True, text

    if text and me.username:
        mention = f"@{me.username}"
        if mention.lower() in text.lower():
            cleaned = re.sub(re.escape(mention), "", text, flags=re.IGNORECASE).strip()
            return True, cleaned or None

    return False, None
