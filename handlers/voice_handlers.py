import html
from aiogram import Router, F
from aiogram.types import Message
from task_queue.enqueue import enqueue_llm_job
from utils.group import gate_group_message, history_key
from utils.reactions import react_seen
from utils.reminders import is_reminder_request
from utils.texts import t
from utils.voice_helper import transcribe_voice

router = Router()

@router.message(F.voice)
async def handle_voice(message: Message, redis):
    # Voice has no caption to mention the bot in, so in groups it only
    # reacts when the voice message replies to one of the bot's messages
    should_handle, _ = await gate_group_message(message, None)
    if not should_handle:
        return
    await react_seen(message)
    bot_message = await message.answer(t("transcribing"), parse_mode="HTML")

    transcription, error = await transcribe_voice(message.bot, message.voice.file_id)
    if error:
        await bot_message.edit_text(error)
        return
    if not transcription.strip():
        await bot_message.edit_text(t("voice_empty"))
        return

    # Let the user know we heard them. Escape: the transcription goes into
    # an HTML-parsed message.
    await bot_message.edit_text(
        t("heard", text=html.escape(transcription)), parse_mode="HTML"
    )

    # "напомни завтра..." spoken aloud becomes a reminder, not a chat turn
    if is_reminder_request(transcription):
        await enqueue_llm_job(
            redis, message, bot_message,
            prompt=transcription,
            history_content="",
            context_type="remind",
            history_id=history_key(message),
        )
        return

    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=transcription,
        history_content=transcription,
        context_type="voice",
        history_id=history_key(message),
    )
