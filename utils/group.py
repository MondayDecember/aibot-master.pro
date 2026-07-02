import random
import re

from aiogram.types import Message

from config import GROUP_CHATTINESS, GROUP_CHATTER_COOLDOWN

# The instruction for a spontaneous remark. Recent group messages come from
# history, so the model sees what people are talking about.
CHATTER_PROMPT = (
    "You are a member of this group chat, not an assistant right now. Read "
    "the recent conversation and drop one short, natural remark - a reaction, "
    "a joke, an opinion or a question. One or two sentences max. Write in the "
    "language of the conversation. Don't introduce yourself, don't offer "
    "help, don't summarize the chat - just chime in like a person would."
)


async def should_chime_in(redis, chat_id: int) -> bool:
    """Roll the dice for a spontaneous group remark, respecting the per-chat
    cooldown (SET NX also makes it race-safe)."""
    if GROUP_CHATTINESS <= 0:
        return False
    if random.random() * 100 >= GROUP_CHATTINESS:
        return False
    acquired = await redis.set(
        f"chatter:{chat_id}", "1", nx=True, ex=GROUP_CHATTER_COOLDOWN
    )
    return bool(acquired)


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
