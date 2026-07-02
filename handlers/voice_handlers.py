import html
import json
from aiogram import Router, F
from aiogram.types import Message
from utils.voice_helper import transcribe_voice

router = Router()

@router.message(F.voice)
async def handle_voice(message: Message, redis):
    bot_message = await message.answer("<i>Transcribing voice message...</i>", parse_mode="HTML")
    
    transcription = await transcribe_voice(message.bot, message.voice.file_id)
    
    if transcription.startswith("Error") or transcription.startswith("Voice transcription is currently"):
        await bot_message.edit_text(transcription)
        return
        
    # Let the user know we heard them
    # Escape: the transcription goes into an HTML-parsed message
    await bot_message.edit_text(
        f"<i>Heard:</i> {html.escape(transcription)}\n\n<i>Thinking...</i>", parse_mode="HTML"
    )
    
    # Queue job for LLM (user message is persisted by the worker, after it fetches history)
    job_data = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "prompt": transcription,
        "history_content": transcription,
        "context_type": "voice",
        "bot_message_id": bot_message.message_id
    }
    
    await redis.rpush("llm_queue", json.dumps(job_data))
