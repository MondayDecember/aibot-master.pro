import html
from aiogram import Router, F
from aiogram.types import Message
from task_queue.enqueue import enqueue_llm_job
from utils.texts import t
from utils.voice_helper import transcribe_voice

router = Router()

@router.message(F.voice)
async def handle_voice(message: Message, redis):
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

    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=transcription,
        history_content=transcription,
        context_type="voice",
    )
